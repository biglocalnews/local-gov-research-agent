# Local Government Research Agent

## TO DO

- Ingest Census list of gov agencies into database (SQLite or Postgres)
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