import cors from 'cors';
import express from 'express';
import { WebSocketServer } from 'ws';

const app = express();
const port = 3000;

app.use(cors());
app.use(express.json());

// 1. Initialize HTTP Server
const server = app.listen(port, () => {
  console.log(`Privex MCP server listening on port ${port}`);
});

// 2. Attach WebSocket Server for real-time UI updates
const wss = new WebSocketServer({ server });

wss.on('connection', (ws) => {
  console.log('React UI connected via WebSocket');
});

// 3. REST endpoint for Python Core -> Express IPC
app.post('/api/alert', (req, res) => {
  console.log('Received alert from Python Core:', req.body);
  
  // 4. Broadcast alert to the React UI
  wss.clients.forEach((client) => {
    if (client.readyState === 1) { // 1 === WebSocket.OPEN
      client.send(JSON.stringify(req.body));
    }
  });

  res.status(200).send('Alert broadcasted to UI');
});