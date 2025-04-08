import asyncio
import json
import os
from typing import Optional, Dict, List, Tuple
from pydantic import BaseModel, Field
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, LLMConfig, CacheMode
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy, BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter, ContentTypeFilter

class MeetingInfo(BaseModel):
    has_website: bool = Field(description="Whether the agency has a functioning website")
    has_website_evidence: str = Field(description="Evidence that the website is functioning", default="")
    
    meeting_schedule_online: bool = Field(description="Whether meeting schedules are posted online")
    schedule_url: Optional[str] = Field(description="URL where meeting schedules can be found", default=None)
    schedule_evidence: str = Field(description="Evidence that meeting schedules are posted online", default="")
    
    agendas_online: bool = Field(description="Whether meeting agendas are posted online")
    agenda_url: Optional[str] = Field(description="URL where meeting agendas can be found", default=None)
    agenda_evidence: str = Field(description="Evidence that meeting agendas are posted online", default="")
    
    minutes_online: bool = Field(description="Whether meeting minutes are posted online")
    minutes_url: Optional[str] = Field(description="URL where meeting minutes can be found", default=None)
    minutes_evidence: str = Field(description="Evidence that meeting minutes are posted online", default="")

# URL scoring keywords
SCHEDULE_KEYWORDS = ["calendar", "event", "meeting", "schedule", "upcoming"]
AGENDA_KEYWORDS = ["agenda", "packet", "material", "board", "commission"]
MINUTES_KEYWORDS = ["minute", "record", "proceeding", "documentation"]

def _score_url(url: str, keywords: List[str]) -> int:
    """Score a URL based on keyword matches"""
    url_lower = url.lower()
    score = 0
    
    # Score URLs that appear to be main section pages higher
    parts = url_lower.split('/')
    if len(parts) <= 4:  # domain.com/section format
        score += 3
    
    # Give higher scores to exact matches in the URL path
    for keyword in keywords:
        if f"/{keyword}" in url_lower or f"/{keyword}s" in url_lower:
            score += 3
        elif keyword in url_lower:
            score += 1
    
    return score

def _process_content_item(content, page_url, results, candidate_urls):
    """Process extracted content and update results"""
    # Website functioning
    if content.get("has_website") is True:
        results["has_website"] = True
        if content.get("has_website_evidence"):
            results["has_website_evidence"] = f"From {page_url}: {content['has_website_evidence']}"
    
    # Meeting schedule
    if content.get("meeting_schedule_online") is True:
        results["meeting_schedule_online"] = True
        if content.get("schedule_url"):
            url = content["schedule_url"]
            score = _score_url(url, SCHEDULE_KEYWORDS)
            candidate_urls["schedule"].append((url, score, page_url))
        if content.get("schedule_evidence"):
            results["schedule_evidence"] = f"From {page_url}: {content['schedule_evidence']}"
    
    # Agendas
    if content.get("agendas_online") is True:
        results["agendas_online"] = True
        if content.get("agenda_url"):
            url = content["agenda_url"]
            score = _score_url(url, AGENDA_KEYWORDS)
            candidate_urls["agenda"].append((url, score, page_url))
        if content.get("agenda_evidence"):
            results["agenda_evidence"] = f"From {page_url}: {content['agenda_evidence']}"
    
    # Minutes
    if content.get("minutes_online") is True:
        results["minutes_online"] = True
        if content.get("minutes_url"):
            url = content["minutes_url"]
            score = _score_url(url, MINUTES_KEYWORDS)
            candidate_urls["minutes"].append((url, score, page_url))
        if content.get("minutes_evidence"):
            results["minutes_evidence"] = f"From {page_url}: {content['minutes_evidence']}"

def _extract_json_content(result, page_url, results, candidate_urls):
    """Extract and process JSON content from a crawl result"""
    try:
        if isinstance(result.extracted_content, str):
            try:
                extracted_data = json.loads(result.extracted_content)
                
                # Handle both dictionary and list responses
                if isinstance(extracted_data, dict):
                    _process_content_item(extracted_data, page_url, results, candidate_urls)
                
                elif isinstance(extracted_data, list):
                    for item in extracted_data:
                        if isinstance(item, dict):
                            _process_content_item(item, page_url, results, candidate_urls)
                
                else:
                    print(f"Unexpected data structure: {type(extracted_data)}")
                
            except json.JSONDecodeError as json_err:
                print(f"⚠️ Could not parse JSON from {page_url}")
                
                # Try to salvage what we can from the text by looking for keywords
                text = result.extracted_content.lower()
                if any(k in text for k in SCHEDULE_KEYWORDS):
                    results["meeting_schedule_online"] = True
                    candidate_urls["schedule"].append((page_url, 1, page_url))
                
                if any(k in text for k in AGENDA_KEYWORDS):
                    results["agendas_online"] = True
                    candidate_urls["agenda"].append((page_url, 1, page_url))
                    
                if any(k in text for k in MINUTES_KEYWORDS):
                    results["minutes_online"] = True
                    candidate_urls["minutes"].append((page_url, 1, page_url))
        
        elif isinstance(result.extracted_content, dict):
            for _, content in result.extracted_content.items():
                if isinstance(content, dict):
                    _process_content_item(content, page_url, results, candidate_urls)
        
        else:
            print(f"Unexpected content type: {type(result.extracted_content)}")
    
    except Exception as content_error:
        print(f"Error processing content: {str(content_error)}")

async def analyze_governance_website(url: str, openai_api_key: str = None):
    """
    Two-phase approach to analyze a local government website for transparency metrics:
    1. First, do a broad but shallow crawl to discover navigation structure
    2. Then do targeted crawls focusing on the most promising sections
    """
    api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or provide as parameter.")
    
    llm_config = LLMConfig(
        provider="openai/gpt-4o-mini",
        api_token=api_key
    )
    
    extraction_instruction = """
    Analyze this government website content to determine:
    1. If the agency has a functioning website
    2. If meeting schedules are posted online (and where)
    3. If meeting agendas are posted online (and where)
    4. If meeting minutes are posted online (and where)
    
    For EACH criterion, provide specific text evidence from the page that supports your assessment.
    Also provide the exact URL where this information was found.
    """
    
    # Browser configuration for all crawls
    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=True,
        viewport_width=1280,
        viewport_height=800,
        java_script_enabled=True,
        verbose=True
    )
    
    results = {
        "has_website": False,
        "has_website_evidence": "",
        "meeting_schedule_online": False,
        "schedule_url": None,
        "schedule_evidence": "",
        "agendas_online": False,
        "agenda_url": None,
        "agenda_evidence": "",
        "minutes_online": False,
        "minutes_url": None,
        "minutes_evidence": ""
    }
    
    # Track candidate URLs for each information type
    candidate_urls = {
        "schedule": [],  # (url, score, source_page)
        "agenda": [],
        "minutes": []
    }
    
    print(f"Starting analysis...")
    
    #-------------------------------------------------------------------
    # PHASE 1: Shallow crawl to discover site structure
    #-------------------------------------------------------------------
    print("\nAnalyzing site structure...")
    
    # Create a shallow BFS crawl strategy to explore the main navigation
    phase1_strategy = BFSDeepCrawlStrategy(
        max_depth=1,  # Just homepage and direct links
        max_pages=10,  # Limit to top navigation pages
        include_external=False
    )
    
    # Simplified LLM extraction for Phase 1
    phase1_llm_strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        schema=MeetingInfo.model_json_schema(),
        extraction_type="schema",
        instruction=extraction_instruction,
        chunk_token_threshold=3000,
        apply_chunking=True
    )
    
    # Configure Phase 1 crawler
    phase1_config = CrawlerRunConfig(
        extraction_strategy=phase1_llm_strategy,
        deep_crawl_strategy=phase1_strategy,
        excluded_tags=["script", "style"],
        exclude_external_links=True,
        cache_mode=CacheMode.ENABLED,
        wait_until="networkidle",
        stream=True,
        verbose=True
    )
    
    # Define URLs to explicitly look for in the main navigation
    important_url_patterns = [
        "/calendar", "/events", "/meeting", "/agenda", "/minute",  
        "/board", "/commission", "/schedule"
    ]
    
    # Run Phase 1 crawl - focus on homepage to find main navigation
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            # First just get the homepage to analyze main navigation
            homepage_config = CrawlerRunConfig(
                extraction_strategy=phase1_llm_strategy,
                excluded_tags=["script", "style"],
                cache_mode=CacheMode.ENABLED,
                wait_until="networkidle",
                verbose=True
            )
            
            # Process homepage
            homepage_result = await crawler.arun(url=url, config=homepage_config)
            
            # Process the homepage content
            if hasattr(homepage_result, 'extracted_content') and homepage_result.extracted_content:
                _extract_json_content(homepage_result, url, results, candidate_urls)
                
                # If homepage has HTML content, we can directly check for important links
                if hasattr(homepage_result, 'cleaned_html') and homepage_result.cleaned_html:
                    html = homepage_result.cleaned_html.lower()
                    
                    # Look for navbar and main menu links
                    import re
                    
                    # Find all anchor tags in the HTML
                    links = re.findall(r'<a\s+[^>]*href=[\'"]([^\'"]*)[\'"][^>]*>(.*?)</a>', html)
                    
                    for href, text in links:
                        # Skip external links or anchors
                        if href.startswith(('#', 'http', 'mailto')):
                            continue
                            
                        # Construct full URL if it's relative
                        full_url = href if href.startswith(('http://', 'https://')) else url.rstrip('/') + '/' + href.lstrip('/')
                        
                        # Score link based on both href and anchor text
                        link_text = text.lower()
                        
                        # Check for calendar/schedule links
                        if any(k in href for k in ['/calendar', '/event', '/meeting', '/schedule']):
                            score = 10  # Higher score for direct navigation links
                            candidate_urls["schedule"].append((full_url, score, "Homepage navigation"))
                            
                        elif any(k in link_text for k in ['calendar', 'event', 'schedule', 'meeting']):
                            score = 8
                            candidate_urls["schedule"].append((full_url, score, "Homepage navigation"))
                            
                        # Check for agenda links
                        if any(k in href for k in ['/agenda', '/packet', '/material']):
                            score = 10
                            candidate_urls["agenda"].append((full_url, score, "Homepage navigation"))
                            
                        elif any(k in link_text for k in ['agenda', 'packet', 'material']):
                            score = 8
                            candidate_urls["agenda"].append((full_url, score, "Homepage navigation"))
                            
                        # Check for minutes links
                        if any(k in href for k in ['/minute', '/record', '/archive']):
                            score = 10
                            candidate_urls["minutes"].append((full_url, score, "Homepage navigation"))
                            
                        elif any(k in link_text for k in ['minute', 'record', 'proceed', 'archive']):
                            score = 8
                            candidate_urls["minutes"].append((full_url, score, "Homepage navigation"))
            
            # Now do a shallow crawl for other pages
            phase1_stream = await crawler.arun(url=url, config=phase1_config)
            
            # Define patterns to skip profile pages
            likely_profile_patterns = ['/supervisor', '/commissioner', '/member', '/official', '/council', '/biography', '/bio']
            
            # Process navigation structure
            async for result in phase1_stream:
                if result.success:
                    page_url = result.url if hasattr(result, 'url') else "unknown"
                    
                    # Skip pages that appear to be about specific people or profiles
                    if any(pattern in page_url.lower() for pattern in likely_profile_patterns):
                        continue
                    
                    # Process content for initial findings
                    if hasattr(result, 'extracted_content') and result.extracted_content:
                        _extract_json_content(result, page_url, results, candidate_urls)
                        
                        # Also add the page URL itself as a candidate if it matches keywords
                        for keyword in SCHEDULE_KEYWORDS:
                            if keyword in page_url.lower():
                                score = _score_url(page_url, SCHEDULE_KEYWORDS)
                                candidate_urls["schedule"].append((page_url, score, "URL pattern"))
                                break
                        
                        for keyword in AGENDA_KEYWORDS:
                            if keyword in page_url.lower():
                                score = _score_url(page_url, AGENDA_KEYWORDS)
                                candidate_urls["agenda"].append((page_url, score, "URL pattern"))
                                break
                        
                        for keyword in MINUTES_KEYWORDS:
                            if keyword in page_url.lower():
                                score = _score_url(page_url, MINUTES_KEYWORDS)
                                candidate_urls["minutes"].append((page_url, score, "URL pattern"))
                                break
            
        except Exception as e:
            print(f"Error during Phase 1: {str(e)}")
        finally:
            # Clean up resources
            if 'phase1_stream' in locals():
                try:
                    await phase1_stream.aclose()
                except Exception:
                    pass
    
    #-------------------------------------------------------------------
    # PHASE 2: Selecting best candidates
    #-------------------------------------------------------------------
    print("\nAnalyzing results...")
    
    # Remove duplicates from candidate lists by URL
    for category in candidate_urls:
        seen_urls = set()
        filtered_candidates = []
        
        for item in candidate_urls[category]:
            url, score, source = item
            if url not in seen_urls:
                seen_urls.add(url)
                filtered_candidates.append(item)
        
        candidate_urls[category] = filtered_candidates
    
    # Select the best candidates based on scores
    for category in candidate_urls:
        if candidate_urls[category]:
            # Sort by score (highest first)
            candidate_urls[category].sort(key=lambda x: x[1], reverse=True)
            
            # Select the top candidate
            if candidate_urls[category]:
                best_url, best_score, best_source = candidate_urls[category][0]
                
                # Update results with the best URL
                if category == "schedule" and best_score > 0:
                    results["schedule_url"] = best_url
                    # Replace evidence if it's from a profile page or not present
                    if not results["schedule_evidence"] or any(pattern in results["schedule_evidence"].lower() for pattern in likely_profile_patterns):
                        results["schedule_evidence"] = f"Found at: {best_url}"
                    results["meeting_schedule_online"] = True
                
                elif category == "agenda" and best_score > 0:
                    results["agenda_url"] = best_url
                    # Replace evidence if it's from a profile page or not present
                    if not results["agenda_evidence"] or any(pattern in results["agenda_evidence"].lower() for pattern in likely_profile_patterns):
                        results["agenda_evidence"] = f"Found at: {best_url}"
                    results["agendas_online"] = True
                
                elif category == "minutes" and best_score > 0:
                    results["minutes_url"] = best_url
                    # Replace evidence if it's from a profile page or not present
                    if not results["minutes_evidence"] or any(pattern in results["minutes_evidence"].lower() for pattern in likely_profile_patterns):
                        results["minutes_evidence"] = f"Found at: {best_url}"
                    results["minutes_online"] = True
    
    # Set website status based on successful crawling
    results["has_website"] = True
    if not results["has_website_evidence"]:
        results["has_website_evidence"] = f"Successfully crawled the website"
    
    # Select the best URLs for each category based on scores
    for category, url_list in candidate_urls.items():
        if url_list:
            url_list.sort(key=lambda x: x[1], reverse=True)
            best_url, score, source = url_list[0]
            
            # Update results with best URLs
            if category == "schedule" and results["meeting_schedule_online"]:
                results["schedule_url"] = best_url
                if not results["schedule_evidence"]:
                    results["schedule_evidence"] = f"Found via {source}"
            
            elif category == "agenda" and results["agendas_online"]:
                results["agenda_url"] = best_url
                if not results["agenda_evidence"]:
                    results["agenda_evidence"] = f"Found via {source}"
            
            elif category == "minutes" and results["minutes_online"]:
                results["minutes_url"] = best_url
                if not results["minutes_evidence"]:
                    results["minutes_evidence"] = f"Found via {source}"
    
    # Print the final results in an easy-to-read format
    print(f"\n=== ANALYSIS RESULTS ===")
    
    print("\n1. WEBSITE STATUS")
    print(f"Has functioning website: {results['has_website']}")
    if results["has_website_evidence"]:
        print(f"Evidence: {results['has_website_evidence']}")
    
    print("\n2. MEETING SCHEDULE")
    print(f"Meeting schedule posted online: {results['meeting_schedule_online']}")
    if results["schedule_url"]:
        print(f"Schedule URL: {results['schedule_url']}")
    if results["schedule_evidence"]:
        print(f"Evidence: {results['schedule_evidence']}")
    
    print("\n3. MEETING AGENDAS")
    print(f"Meeting agendas posted online: {results['agendas_online']}")
    if results["agenda_url"]:
        print(f"Agenda URL: {results['agenda_url']}")
    if results["agenda_evidence"]:
        print(f"Evidence: {results['agenda_evidence']}")
    
    print("\n4. MEETING MINUTES")
    print(f"Meeting minutes posted online: {results['minutes_online']}")
    if results["minutes_url"]:
        print(f"Minutes URL: {results['minutes_url']}")
    if results["minutes_evidence"]:
        print(f"Evidence: {results['minutes_evidence']}")
    
    return results

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze local government websites for basic meeting information")
    parser.add_argument("--url", type=str, required=True, help="URL of the government website to analyze")
    parser.add_argument("--api-key", type=str, help="OpenAI API key (will use OPENAI_API_KEY env var if not provided)")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(analyze_governance_website(args.url, args.api_key))
    except KeyboardInterrupt:
        print("\nCrawl interrupted by user.")
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")
