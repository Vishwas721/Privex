# Privex Neo4j Graph Schema

## Purpose
This database acts as the relational "Prefrontal Cortex" for the Privex Memory Agent. It tracks the specific relationships between applications, sensitive data, and temporal events.

## 1. Nodes (Entities)
* `(:Application {name: String})` - Represents software (e.g., 'Visual Studio Code', 'Google Chrome').
* `(:Secret {type: String, redacted_preview: String})` - Represents a high-risk item caught by the Visual Firewall (e.g., type: 'AWS Key', redacted_preview: 'AKIA...').
* `(:Alert {id: String, timestamp: String, risk_level: String})` - Represents the specific firewall event.
* `(:Date {date: String})` - Represents the day the event occurred (YYYY-MM-DD) to allow for temporal queries.

## 2. Relationships (Edges)
* `(:Alert) -[:OCCURRED_IN]-> (:Application)` - Links an alert to the app where it happened.
* `(:Alert) -[:EXPOSED]-> (:Secret)` - Links an alert to the specific secret that was caught.
* `(:Alert) -[:HAPPENED_ON]-> (:Date)` - Links an alert to the day it occurred.

## 3. Example Cypher Query
To find all apps where an AWS Key was exposed today:
`MATCH (a:Application)<-[:OCCURRED_IN]-(evt:Alert)-[:EXPOSED]->(s:Secret {type: 'AWS Key'}), (evt)-[:HAPPENED_ON]->(d:Date {date: '2026-04-14'}) RETURN a.name`