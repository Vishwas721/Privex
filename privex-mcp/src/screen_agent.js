import 'dotenv/config';
import { activeWindow } from 'active-win';
import screenshot from 'screenshot-desktop';
import sharp from 'sharp';

// The .env should be: AI_CORE_URL=http://localhost:8000/api/analyze-frame
const AI_CORE_URL = process.env.AI_CORE_URL; 
const FRAME_INTERVAL_MS = 200;
const REQUEST_TIMEOUT_MS = 5000;
if (!AI_CORE_URL) {
  console.error('AI_CORE_URL is not set. Screen agent will fail.');
}

async function captureAndSendFrame() {
  try {
    // 1. Capture Screen
    const screenBuffer = await screenshot({ format: 'png' });

    // 2. Downscale (Visual Firewall constraint)
    // 2. Downscale (Optimized for BOTH YOLO and OCR)
    const resizedBuffer = await sharp(screenBuffer)
      .resize({ width: 1280 }) // Big enough for OCR to actually read the text
      .jpeg({ quality: 70 })   // Compress the file size so it doesn't crash the API
      .toBuffer();

    const base64Image = resizedBuffer.toString('base64');
    console.log(`Captured frame at ${Date.now() / 1000}`);
    console.log(`[MCP] Captured frame. Size: ${base64Image.length} bytes.`);

    const win = await activeWindow();

    const activeApp = win
     ? {
         title: win.title || '',
         owner: win.owner?.name || '',
      }
     : null;

    // 3. Construct the EXACT payload FastAPI expects
    const payload = {
      base64_image: base64Image, // FIXED: Matches schemas.py
      timestamp: Date.now() / 1000.0,
      source: "screen_mcp",
      active_app: activeApp,
    };

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      // 4. Send to the exact URL from the .env (No double-stacking)
      const response = await fetch(AI_CORE_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      console.log("[MCP-Agent] Frame successfully delivered to Core.");

      if (!response.ok) {
        console.error(`[MCP-ERROR] Frame POST failed: ${response.status}`);
      } else {
        console.log(`[MCP] Payload successfully sent to Port 8000.`);
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        console.error(`[MCP-ERROR] Frame POST timed out.`);
      } else {
        console.error('[MCP-ERROR] Frame POST error FULL:', error);
      }
    } finally {
      clearTimeout(timeout);
    }
  } catch (error) {
    console.error('[MCP-ERROR] Capture cycle error:', error.message);
  } finally {
    // Safely loop every 2 seconds
    setTimeout(captureAndSendFrame, FRAME_INTERVAL_MS);
  }
}

console.log("🛡️ Privex Visual Firewall: Autopilot Engaged.");
captureAndSendFrame();