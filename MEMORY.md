# Memory systems and query flow

Inspired by the Rosston Agentic Memory System [https://www.rosston.dev/blog/groundhog-day]()

This document describes how user queries are interpreted and answered using three memory systems (Short-Term, Episodic, and Semantic), and how responses are written back to long-term memory.

```mermaid
flowchart LR
  userQuery[User Query] --> aiIntention["AI: What is this user's intentions based on what we know, generate a new query to run against our various tools that would satisfy the request."]
  aiIntention --> toolQuery[Generated query to tools]

  subgraph tools [Memory tools]
    shortTermMemory[Short-Term Memory: Session History, recall from previous conversations]
    episodicRecall[Episodic Memory: Past events, summarize and save, recall via Vector Search]
    semanticRecall[Semantic Memory: Facts and knowledge, save and recall exact information e.g. USER lives in a house under a bridge]
  end

  toolQuery --> shortTermMemory
  toolQuery --> episodicRecall
  toolQuery --> semanticRecall

  shortTermMemory --> combinedResults[Combined results]
  episodicRecall --> combinedResults
  semanticRecall --> combinedResults

  combinedResults --> presentToUser[Present to user]

  presentToUser --> commitEpisodic[Commit summary to Episodic Memory]
  presentToUser --> commitSemantic[Commit summary to Semantic Memory]
```