# Local Government Research Agent

R&D on use of agents to assist with metadata gathering around local
government meetings and resources (agendas, minutes, meeting videos,
etc.).

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

## Web Research via Claude Desktop + MCP

To tinker with Claude as a research agent that drives the browser for gathering
agency metadata, install and configure the following:

- Claude Desktop
- A browser automation plugin for Claude Desktop that supports the [Model Context Protocol](https://github.com/modelcontextprotocol/servers) such as [playwright-mcp](https://github.com/microsoft/playwright-mcp)

## Data sources

- [Census list of gov entities](https://www.census.gov/data/tables/2022/econ/gus/2022-governments.html)
