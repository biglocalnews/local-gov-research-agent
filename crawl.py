import asyncio
import os
from typing import List, Optional
from pydantic import BaseModel, Field
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, LLMConfig, CacheMode
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter, ContentTypeFilter

# Define schema for governance criteria assessment
class MeetingInfo(BaseModel):
    has_website: bool = Field(description="Whether the agency has a functioning website")
    meeting_schedule_online: bool = Field(description="Whether meeting schedules are posted online")
    schedule_url: Optional[str] = Field(description="URL where meeting schedules can be found", default=None)
    
    agendas_online: bool = Field(description="Whether meeting agendas are posted online")
    agenda_url: Optional[str] = Field(description="URL where meeting agendas can be found", default=None)
    
    minutes_online: bool = Field(description="Whether meeting minutes are posted online")
    minutes_url: Optional[str] = Field(description="URL where meeting minutes can be found", default=None)
    minutes_include_required_details: bool = Field(description="Whether minutes include required details such as votes, discussion summaries, and attendance")
    
    recordings_available: bool = Field(description="Whether meeting recordings or livestreams are available")
    recording_url: Optional[str] = Field(description="URL where recordings can be accessed", default=None)
    
    no_advance_registration: bool = Field(description="Whether public can comment without advance registration")
    can_discuss_any_topic: bool = Field(description="Whether public commenters can discuss any relevant topic")
    adequate_comment_time: bool = Field(description="Whether adequate time (1hr+) is allocated for public comment")
    
    rarely_cancelled: bool = Field(description="Whether meetings are rarely cancelled")
    varied_meeting_times: bool = Field(description="Whether meeting times vary to accommodate different schedules")
    
    evidence: str = Field(description="Text evidence supporting the assessment of each criterion")

async def analyze_governance_website(url: str, openai_api_key: str = None):
    """
    Crawls and analyzes a local government website to assess governance criteria.
    
    Args:
        url: The website URL to analyze
        openai_api_key: OpenAI API key (defaults to environment variable)
    """
    # Use provided key or get from environment
    api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or provide as parameter.")
    
    # Configure LLM extraction strategy
    llm_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="openai/gpt-4o-mini",
            api_token=api_key
        ),
        schema=MeetingInfo.model_json_schema(),
        extraction_type="schema",
        instruction="""
        Analyze this government website content to assess transparency and accessibility criteria.
        Search for information about public meetings including schedules, agendas, minutes, recordings,
        and public comment policies. Look for evidence of each criterion and extract URLs where this information can be found.
        For 'evidence', provide specific text from the page that supports your assessment for each criterion.
        """,
        chunk_token_threshold=4000,  # Larger chunks for better context
        apply_chunking=True,
        overlap_rate=0.1
    )
    
    # Create keyword relevance scorer to prioritize governance-related pages
    keyword_scorer = KeywordRelevanceScorer(
        keywords=["meeting", "agenda", "minutes", "schedule", "recording", "livestream", 
                 "public comment", "public hearing", "board", "commission", "calendar"],
        weight=0.8  # High weight for keyword relevance
    )
    
    # Create filter chain for targeting specific content
    filter_chain = FilterChain([
        # Only include HTML content
        ContentTypeFilter(allowed_types=["text/html"]),
        
        # Target URLs likely to contain governance information
        URLPatternFilter(patterns=[
            "*meeting*", "*agenda*", "*minutes*", "*calendar*", "*schedule*", "*board*", 
            "*commission*", "*video*", "*audio*", "*recording*", "*livestream*", 
            "*comment*", "*public*", "*legislation*"
        ])
    ])
    
    # Configure the BestFirstCrawlingStrategy with our scorer and filter
    deep_crawl_strategy = BestFirstCrawlingStrategy(
        max_depth=3,  # Go 3 levels deep 
        max_pages=40,  # Limit to 40 pages for manageable results
        include_external=False,  # Only stay on the same domain
        url_scorer=keyword_scorer,
        filter_chain=filter_chain
    )
    
    # Cache mode already imported at the top
    
    # Configure crawler with optimized settings from documentation
    crawler_config = CrawlerRunConfig(
        extraction_strategy=llm_strategy,
        deep_crawl_strategy=deep_crawl_strategy,
        
        # Content filtering
        word_count_threshold=10,  # Skip pages with very little content
        excluded_tags=["nav", "footer", "header", "script", "style", "aside", "sidebar"],  # Skip non-content elements
        exclude_external_links=True,  # Stay on target domain
        css_selector="main, #content, .content, article, .page-content, #main-content, body",  # Focus on main content areas
        
        # Performance options
        cache_mode=CacheMode.ENABLED,  # Enable caching for better performance
        
        # Page navigation & timing (moved from BrowserConfig)
        wait_until="networkidle",  # Wait until network is idle before considering page loaded
        page_timeout=10000,  # Longer timeout (10s) for pages to fully load
        
        # Extra features
        screenshot=True,  # Capture screenshots for verification
        
        # JS interactions (uncomment if needed for specific sites with dynamic content)
        # js_code=["document.querySelectorAll('button.load-more').forEach(btn => btn.click())"],  # Click "load more" buttons
        # wait_for="css:.main-content-loaded",  # Wait for specific element to load
        
        # Streaming and display
        stream=True,  # Enable streaming for faster processing with BestFirstCrawling
        verbose=True  # Show detailed logs
    )
    
    # Browser configuration - optimized for better performance and reliability
    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=True,
        viewport_width=1280,
        viewport_height=800,  # Larger viewport for better content visibility
        text_mode=False,  # Keep images to help with content context
        light_mode=True,  # Turn off background features for better performance
        java_script_enabled=True,  # Correct parameter name per docs
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",  # Modern user agent
        verbose=True,  # Print extra logs for debugging
        extra_args=["--disable-extensions", "--disable-gpu", "--disable-dev-shm-usage"]  # Additional performance optimizations
    )
    
    print(f"Starting analysis of {url}...")
    
    # Results container
    all_results = {}
    found_pages = 0
    
    # Run crawler with streaming results
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Using streaming mode with BestFirstCrawling for better results
        try:
            # Get async iterator for streamed results
            results_stream = await crawler.arun(url=url, config=crawler_config)
            
            print("\n=== Processing results as they become available ===\n")
            
            async for result in results_stream:
                if result.success:
                    found_pages += 1
                    
                    # Process and store this page's results
                    if hasattr(result, 'extracted_content') and isinstance(result.extracted_content, dict):
                        for path, content in result.extracted_content.items():
                            if isinstance(content, List):
                                for item in content:
                                    if isinstance(item, dict) and item.get("evidence"):
                                        # Truncate evidence for display
                                        item["evidence"] = item["evidence"][:200] + "..." if len(item["evidence"]) > 200 else item["evidence"]
                            
                            # Store in our results dictionary
                            all_results[path] = content
                    else:
                        # Handle case where extracted_content is not a dictionary
                        path = result.url if hasattr(result, 'url') else f"page_{found_pages}"
                        content = result.extracted_content if hasattr(result, 'extracted_content') else "No content extracted"
                        all_results[path] = content
                    
                    # Show progress
                    page_url = result.url if hasattr(result, 'url') else f"page_{found_pages}"
                    print(f"\nProcessed page {found_pages}: {page_url}")
                    if hasattr(result, 'metadata') and isinstance(result.metadata, dict):
                        print(f"Score: {result.metadata.get('score', 0):.2f} | Depth: {result.metadata.get('depth', 0)}")
                else:
                    print(f"Error processing page: {result.error_message}")
            
            # Show final results summary
            print(f"\n=== Finished crawling {found_pages} pages ===\n")
            
            # Display all results
            for path, content in all_results.items():
                print(f"\nResults for {path}:")
                print(content)
            
            # Show LLM usage stats if the method exists
            if hasattr(llm_strategy, 'show_usage') and callable(llm_strategy.show_usage):
                try:
                    llm_strategy.show_usage()
                except Exception as e:
                    print(f"Could not show LLM usage stats: {str(e)}")
            
            return all_results
        except Exception as e:
            print(f"Error during crawl: {str(e)}")
            return None

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze local government websites for transparency criteria")
    parser.add_argument("--url", type=str, default="https://sfbos.org/", help="URL of the government website to analyze")
    parser.add_argument("--api-key", type=str, help="OpenAI API key (will use OPENAI_API_KEY env var if not provided)")
    
    args = parser.parse_args()
    
    asyncio.run(analyze_governance_website(args.url, args.api_key))
