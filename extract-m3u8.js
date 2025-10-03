const { chromium } = require('playwright');

(async () => {
  const targetUrl = process.argv[2];
  if (!targetUrl) {
    process.exit(1);
  }

  const browser = await chromium.launch({
    headless: false,
    channel: 'chrome',
    args: [
      '--disable-blink-features=AutomationControlled',
      '--autoplay-policy=no-user-gesture-required'
    ]
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 }
  });

  const page = await context.newPage();

  await page.route('**/*qzzzzzzzzzqq.com**', route => route.abort());
  await page.route('**/*realxxx.com**', route => route.abort());

  const responses = [];
  page.on('response', response => {
    const url = response.url();
    if (url.includes('.m3u8')) {
      responses.push(url);
    }
  });

  try {
    await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 15000 });

    const playerSelectors = ['#player', '.player', '[data-player]', 'video', 'iframe'];
    let playerElement = null;
    
    for (const selector of playerSelectors) {
      try {
        playerElement = await page.locator(selector).first();
        if (await playerElement.isVisible({ timeout: 2000 })) {
          break;
        }
      } catch (e) {
        continue;
      }
    }

    if (playerElement) {
      try {
        const [response] = await Promise.all([
          page.waitForResponse(
            res => res.url().includes('.m3u8'),
            { timeout: 10000 }
          ),
          playerElement.click({ force: true })
        ]);
        
        console.log(response.url());
        await browser.close();
        process.exit(0);
      } catch (e) {}
    }

    if (responses.length > 0) {
      console.log(responses[0]);
      await browser.close();
      process.exit(0);
    } else {
      await browser.close();
      process.exit(1);
    }
  } catch (e) {
    await browser.close();
    process.exit(1);
  }
})();
