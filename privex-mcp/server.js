import cors from 'cors';
import express from 'express';
import { WebSocketServer } from 'ws';

const app = express();
const port = 3000;

app.use(cors({ origin: 'http://localhost:5173' }));
app.use(express.json());

// NEW: Proxy the request to the Python Core (which queries PostgreSQL)
app.get('/api/logs', async (req, res) => {
  const limit = req.query.limit || '50';
  // Use environment variable with fallback to native loopback
  const coreApiUrl = process.env.CORE_API_URL || 'http://127.0.0.1:8000';

  try {
    const response = await fetch(`${coreApiUrl}/api/logs?limit=${limit}`);

    if (!response.ok) {
      throw new Error(`Python Core returned status: ${response.status}`);
    }

    const data = await response.json();
    res.status(200).json(data);
  } catch (error) {
    console.error('Failed to fetch logs from PostgreSQL via Python Core:', error);
    res.status(500).json({ error: 'Failed to fetch secure audit ledger' });
  }
});

// 1. Initialize HTTP Server
const server = app.listen(port, '0.0.0.0', () => {
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