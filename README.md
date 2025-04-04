# Local Government Research Agent

R&D on use of agents to assist with metadata gathering around local
government meetings and resources (agendas, minutes, meeting videos,
etc.).

## User stories

- What are the agency meetings in my community?
- What information is missing? Can you help me find details about meetings that are missing information I need?
- What types of information is most important for me to know what's worth covering? (Date, time of meeting start, additional side-meetings, agenda, packets, transcripts, audio, cancelled?, deleted?, time-changed?)
- Where should I deploy reporters/documenters? What upcoming meetings look like they will be most crucial to cover and don't have associated information?

## Web Research via Claude Desktop + MCP

To tinker with Claude as a research agent that drives the browser for gathering
agency metadata, install and configure the following:

- Claude Desktop
- A browser automation plugin for Claude Desktop that supports the [Model Context Protocol](https://github.com/modelcontextprotocol/servers) such as [playwright-mcp](https://github.com/microsoft/playwright-mcp)

## Data sources

- [Census list of gov entities](https://www.census.gov/data/tables/2022/econ/gus/2022-governments.html)

