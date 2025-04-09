# Local Government Research Agent

## TO DO

- Ingest Census list of gov agencies into database (SQLite or Postgres)
  - Supplemenet this list with additional bodies from US territories       
  - Create table(s) or interoperate with Metadata admin?
- Install [playwright-mcp](https://github.com/microsoft/playwright-mcp)
- Custom Model Context Protocol server to inject metadata into the database


## Agent tasks

- Find agency website
- Find agenda and meetings page
- Find where meeting videos/audio are posted
- Find all decision-making and advisory bodies
- Find meeting dates of all bodies
- Emit structured data (e.g. JSON) for location of agendas, etc and entity metadata
- Identify civic data platform, if any (e.g. CivicPlus, Legistar)


## User stories

- What are the agency meetings in my community?
- What information is missing? Can you help me find details about meetings that are missing information I need?
- What types of information is most important for me to know what's worth covering? (Date, time of meeting start, additional side-meetings, agenda, packets, transcripts, audio, cancelled?, deleted?, time-changed?)
- Where should I deploy reporters/documenters? What upcoming meetings look like they will be most crucial to cover and don't have associated information?

## Meeting crawler script

The `tests/crawl.py` script uses the `crawl4ai` library to extract structured meeting information from a given local government website.

The script performs two actions:

1. **Discovery**: Uses breadth-first crawling to find pages containing meeting information
2. **Extraction**: Calls an LLM to parse meeting details from discovered pages

It outputs structured meeting data, including:
- Meeting dates and times
- Convening bodies
- Agenda and minutes URLs
- Meeting locations and titles

Currently it just prints the results.

### Usage

The script requires an API key that corresponds to the model called in the script (currently OpenAI's `gpt-4o-mini`.) You can provide the key via `--api-key` argument or `OPENAI_API_KEY` environment variable.



```bash
# Install dependencies using uv
uv sync

# Run the script
uv run tests/crawl.py --url "https://example.gov"

# If you want to pass an API key directly
uv run tests/crawl.py --url "https://example.gov" --api-key "your-api-key"
```

### Testing notes

The script works on the following sites:
1. [SF Board of Supervisors](https://sfbos.org/)
1. 

The script fails on the following sites:
1. [Seattle City Council](https://www.seattle.gov/council) (reason: schedule is in a Google Calendar iframe)
1. [Brainerd School Board](https://www.isd181.org/district/board_of_education) (reason: schedule is in a Google Calendar iframe)
1. [Austin City Council](https://www.austintexas.gov/austin-city-council) (reason: crawler max set too low for this big a site)