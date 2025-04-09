import asyncio
import os
import json
from datetime import datetime
import pytz
from typing import Optional, List
from pydantic import BaseModel, Field, ValidationError
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, LLMConfig, CacheMode
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
import re


# Data models for structured meeting information
class Meeting(BaseModel):
    convening_body: str = Field(description="Name of the body/committee holding the meeting")
    date: datetime = Field(description="Date and time of the meeting")
    agenda_url: Optional[str] = Field(description="URL to the meeting agenda if available", default=None)
    minutes_url: Optional[str] = Field(description="URL to the meeting minutes if available", default=None)
    title: Optional[str] = Field(description="Title or description of the meeting if available", default=None)
    location: Optional[str] = Field(description="Location of the meeting if available", default=None)


class MeetingInfo(BaseModel):
    meetings: List[Meeting] = Field(description="List of all extracted meetings", default_factory=list)


def process_content_item(content: dict, page_url: str, results: dict):
    """
    Processes extracted content from a webpage and adds valid meetings to the results.
    Handles both JSON string and dictionary inputs, validates meeting data against the Meeting model.
    """
    meetings_to_process = []
    
    # Handle string input (JSON)
    if isinstance(content, str):
        try:
            meetings_to_process = json.loads(content)
        except json.JSONDecodeError:
            return
    # Handle dict/list input
    elif isinstance(content, (dict, list)):
        meetings_to_process = content if isinstance(content, list) else [content]
    else:
        return

    if not meetings_to_process:
        return
    
    for meeting_data in meetings_to_process:
        if isinstance(meeting_data, dict):
            try:
                # Remove any extra fields not in our model
                valid_fields = {'convening_body', 'date', 'agenda_url', 'minutes_url', 'title', 'location'}
                cleaned_data = {k: v for k, v in meeting_data.items() if k in valid_fields}
                meeting_obj = Meeting(**cleaned_data)
                results["meetings"].append(meeting_obj)
            except ValidationError:
                continue
            except Exception:
                continue
        else:
            continue


def print_results(results: dict):
    """Prints the final analysis results, showing upcoming and past meetings in chronological order."""
    print(f"\n=== ANALYSIS RESULTS ===")
    
    print("\n1. UPCOMING MEETINGS")
    if results["upcoming_meetings"]:
        for meeting in sorted(results["upcoming_meetings"], key=lambda x: x.date)[:5]:
            print(f"\n{meeting.convening_body} - {meeting.date.strftime('%Y-%m-%d %H:%M')}")
            if meeting.title:
                print(f"Title: {meeting.title}")
            if meeting.location:
                print(f"Location: {meeting.location}")
            if meeting.agenda_url:
                print(f"Agenda: {meeting.agenda_url}")
    else:
        print("No upcoming meetings found")
    
    print("\n2. PAST MEETINGS")
    if results["past_meetings"]:
        for meeting in sorted(results["past_meetings"], key=lambda x: x.date, reverse=True)[:5]:
            print(f"\n{meeting.convening_body} - {meeting.date.strftime('%Y-%m-%d %H:%M')}")
            if meeting.title:
                print(f"Title: {meeting.title}")
            if meeting.location:
                print(f"Location: {meeting.location}")
            if meeting.agenda_url:
                print(f"Agenda: {meeting.agenda_url}")
            if meeting.minutes_url:
                print(f"Minutes: {meeting.minutes_url}")
    else:
        print("No past meetings found")


def deduplicate_meetings(meetings: List[Meeting]) -> List[Meeting]:
    """
    Removes duplicate meetings based on date and convening body.
    Keeps the meeting entry with more information (prefers entries with agenda/minutes URLs).
    """
    unique_meetings = {}
    for meeting in meetings:
        key = (meeting.date, meeting.convening_body)
        if key not in unique_meetings or (
            (meeting.agenda_url and not unique_meetings[key].agenda_url) or
            (meeting.minutes_url and not unique_meetings[key].minutes_url)
        ):
            unique_meetings[key] = meeting
    
    return list(unique_meetings.values())


def score_title(title: Optional[str], keywords: List[str]) -> int:
    """Scores page titles based on the presence of meeting-related keywords."""
    if not title:
        return 0
    title_lower = title.lower()
    score = 0
    for keyword in keywords:
        if keyword.lower() in title_lower:
            score += 1
    return score


async def analyze_governance_website(url: str, openai_api_key: str = None):
    """
    Main function to analyze a local government website for meeting information.
    Uses a two-phase approach:
    1. Discovery: Finds relevant pages using BFS crawling and keyword scoring
    2. Extraction: Uses LLM to extract meeting details from the most relevant pages

    Args:
        url: The starting URL of the government website
        openai_api_key: Optional API key for OpenAI (falls back to environment variable)
    """
    api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or provide as parameter.")
    
    # LLM configuration for meeting extraction
    llm_config = LLMConfig(
        provider="openai/gpt-4o-mini", 
        api_token=api_key,
        temprature=0.2,
        max_tokens=1500
    )
    
    # Instructions for the LLM to extract meeting information
    extraction_instruction = """
    Analyze the HTML content of this government calendar or meetings page.
    Extract ALL meetings listed in the page's table structure, including both past and upcoming meetings.
    Pay special attention to any embedded calendars or iframes (like Google Calendar) - these often contain the most up-to-date meeting information.
    
    For each meeting:
    - Extract the committee/board name from the meeting link text
    - Convert the date and time to ISO format with timezone (e.g. 2024-03-31T09:30:00-07:00)
    - Include the full URL for any agenda or minutes links
    - Capture the location exactly as shown
    - Include any meeting title or description if available
    
    For embedded calendars:
    - Look for calendar events and extract their details
    - Pay attention to recurring events and series
    - Note any links to agendas or minutes within the calendar entries
    - Capture the full event description if available
    
    Do not skip any meetings, and ensure all dates are properly formatted with timezone information.
    """
    
    # Browser configuration for web crawling
    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=True,
        viewport_width=1920,  # Increased for better calendar display
        viewport_height=1080,
        java_script_enabled=True,
        verbose=True,
        ignore_https_errors=True,  # Some sites have mixed content
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        text_mode=False,  # Keep images enabled for calendar embeds
        light_mode=False  # Keep full browser features for calendar embeds
    )
    
    results = {
        "meetings": []
    }
    
    print("Starting analysis...")
    
    # Phase 1: Discovery - Find pages likely to contain meeting information
    print("\nPHASE 1: Discovering relevant pages...")
    
    meeting_keywords = ["meeting", "agenda", "minutes", "calendar", "event"]
    
    discovery_config = CrawlerRunConfig(
        deep_crawl_strategy=BFSDeepCrawlStrategy(
            max_depth=2,
            max_pages=20,
            include_external=False,
        ),
        scraping_strategy=LXMLWebScrapingStrategy(),
        excluded_tags=["style", "nav", "footer", "header", "aside"],  # Removed script from excluded tags
        exclude_external_links=True,
        cache_mode=CacheMode.ENABLED,
        wait_until="networkidle",  # Wait for network to be idle to ensure iframes load
        stream=True,
        verbose=True
    )
    
    discovered_pages = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            discovery_stream = await crawler.arun(url=url, config=discovery_config)
            
            async for result in discovery_stream:
                if result.success and hasattr(result, 'url') and result.html:
                    title_match = re.search(r'<title.*?>(.*?)</title>', result.html, re.IGNORECASE | re.DOTALL)
                    title = title_match.group(1).strip() if title_match else "[No Title Found]"
                    calculated_score = score_title(title, meeting_keywords)
                    discovered_pages.append({"url": result.url, "score": calculated_score, "title": title})
                elif result.success and hasattr(result, 'url'):
                    discovered_pages.append({"url": result.url, "score": 0, "title": "[HTML Error/Missing]"})

        except Exception as e:
            print(f"Error during Phase 1 (Discovery): {str(e)}")
        finally:
            if 'discovery_stream' in locals():
                try:
                    await discovery_stream.aclose()
                except Exception: pass

        # Deduplicate pages and select top candidates
        unique_pages_dict = {}
        for page in discovered_pages:
            url = page['url']
            if url not in unique_pages_dict or page['score'] > unique_pages_dict[url]['score']:
                unique_pages_dict[url] = page
        
        deduplicated_pages = list(unique_pages_dict.values())
        deduplicated_pages.sort(key=lambda x: x['score'], reverse=True)
        top_n = 10
        candidate_urls = [page['url'] for page in deduplicated_pages[:top_n] if page['score'] > 0]

        if not candidate_urls:
            print("\nNo relevant pages found based on keywords. Skipping extraction.")
            print_results(results)
            return results
            
        print(f"\nAnalyzing {len(candidate_urls)} relevant pages...")

        # Phase 2: Extract meetings from candidate pages
        print("\nPHASE 2: Extracting meetings from candidate pages...")
        
        for candidate_url in candidate_urls:
            print(f"  Processing: {candidate_url}")
            try:
                # Create fresh LLM strategy for each page
                llm_strategy = LLMExtractionStrategy(
                    llm_config=llm_config,
                    schema=MeetingInfo.model_json_schema(),
                    extraction_type="schema",
                    instruction=extraction_instruction,
                    chunk_token_threshold=3000,
                    overlap_rate=0.1,
                    apply_chunking=True,
                    input_format="html",
                    verbose=True
                )
                
                extraction_config = CrawlerRunConfig(
                    extraction_strategy=llm_strategy,
                    excluded_tags=["script", "style", "nav", "footer", "header", "aside"],
                    cache_mode=CacheMode.BYPASS,
                    wait_until="networkidle",
                    verbose=True
                )
                
                extraction_result = await crawler.arun(url=candidate_url, config=extraction_config)
                
                if extraction_result.success and hasattr(extraction_result, 'extracted_content'):
                    process_content_item(extraction_result.extracted_content, candidate_url, results)
            
            except Exception as e:
                print(f"Error processing {candidate_url}: {str(e)}")

    # Deduplicate all meetings first
    all_meetings = deduplicate_meetings(results["meetings"])
    
    # Now categorize into past and upcoming
    now = datetime.now(pytz.UTC)  # Get current time in UTC
    past_meetings = []
    upcoming_meetings = []

    for meeting in all_meetings:
        # If meeting.date doesn't have tzinfo, assume it's in UTC
        meeting_date = meeting.date if meeting.date.tzinfo else pytz.UTC.localize(meeting.date)
        if meeting_date < now:
            past_meetings.append(meeting)
        else:
            upcoming_meetings.append(meeting)
    
    # Sort the categorized meetings
    past_meetings.sort(key=lambda x: x.date.astimezone(pytz.UTC), reverse=True)
    upcoming_meetings.sort(key=lambda x: x.date.astimezone(pytz.UTC))

    results = {
        "past_meetings": past_meetings[:5],
        "upcoming_meetings": upcoming_meetings[:5]
    }

    print_results(results)
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
