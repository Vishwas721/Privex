import 'dotenv/config';
import screenshot from 'screenshot-desktop';
import sharp from 'sharp';

// The .env should be: AI_CORE_URL=http://localhost:8000/api/analyze-frame
const AI_CORE_URL = process.env.AI_CORE_URL; 
const FRAME_INTERVAL_MS = 2000;
const REQUEST_TIMEOUT_MS = 5000;

if (!AI_CORE_URL) {
  console.error('AI_CORE_URL is not set. Screen agent will fail.');
}

async function captureAndSendFrame() {
  try {
    // 1. Capture Screen
    const screenBuffer = await screenshot({ format: 'png' });

    // 2. Downscale (Visual Firewall constraint)
    const resizedBuffer = await sharp(screenBuffer)
      .resize({
        width: 640,
        height: 640,
        fit: 'contain',
      })
      .png()
      .toBuffer();

    const base64Image = resizedBuffer.toString('base64');
    console.log(`[MCP] Captured frame. Size: ${base64Image.length} bytes.`);

    // 3. Construct the EXACT payload FastAPI expects
    const payload = {
      image_base64: base64Image,
      timestamp: Date.now() / 1000.0,
      source: "screen_mcp" // Added missing source key
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