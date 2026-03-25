import 'dotenv/config';
import screenshot from 'screenshot-desktop';
import sharp from 'sharp';

const AI_CORE_URL = process.env.AI_CORE_URL;
const FRAME_INTERVAL_MS = 2000;
const REQUEST_TIMEOUT_MS = 1000;

if (!AI_CORE_URL) {
  console.error('AI_CORE_URL is not set. Screen agent will continue running and retry after each cycle.');
}

async function captureAndSendFrame() {
  try {
    const screenBuffer = await screenshot({ format: 'png' });

    const resizedBuffer = await sharp(screenBuffer)
      .resize({
        width: 640,
        height: 640,
        fit: 'contain',
      })
      .png()
      .toBuffer();

    const base64Image = resizedBuffer.toString('base64');
    console.log(`Captured frame (base64 length): ${base64Image.length}`);

    const payload = {
      base64_image: base64Image,
      timestamp: Date.now()/1000.0, 
    };

    if (!AI_CORE_URL) {
      throw new Error('Missing AI_CORE_URL environment variable.');
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch(`${AI_CORE_URL}/api/analyze-frame`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok) {
        const responseText = await response.text().catch(() => 'Unable to read response body');
        console.error(`Frame POST failed: ${response.status} ${response.statusText}. Body: ${responseText}`);
      }
    } catch (error) {
      if (error && error.name === 'AbortError') {
        console.error(`Frame POST timed out after ${REQUEST_TIMEOUT_MS}ms`);
      } else {
        console.error('Frame POST error:', error);
      }
    } finally {
      clearTimeout(timeout);
    }
  } catch (error) {
    console.error('Capture/process cycle error:', error);
  } finally {
    setTimeout(() => {
      captureAndSendFrame().catch((loopError) => {
        console.error('Unexpected loop error:', loopError);
      });
    }, FRAME_INTERVAL_MS);
  }
}

captureAndSendFrame().catch((startupError) => {
  console.error('Screen agent failed to start:', startupError);
});
