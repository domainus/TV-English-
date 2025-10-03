const { chromium } = require('playwright');

(async () => {
  const targetUrl = process.argv[2];
  if (!targetUrl) {
    process.exit(1);
  }

  const browser = await chromium.launch({
    headless: true, // Obbligatorio per l'esecuzione su server
    args: [
      '--disable-blink-features=AutomationControlled',
      '--autoplay-policy=no-user-gesture-required'
    ]
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    // Bypassa la geolocalizzazione e il fuso orario per sembrare un utente normale
    locale: 'it-IT',
    timezoneId: 'Europe/Rome',
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
    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 25000 });

    // Tenta di chiudere i banner dei cookie/privacy
    const cookieBanners = [
      page.locator('button:has-text("Accept")'),
      page.locator('button:has-text("Agree")'),
      page.locator('button:has-text("Accetta")'),
      page.locator('button:has-text("Consenti")')
    ];
    for (const banner of cookieBanners) {
      await banner.click({ timeout: 1000 }).catch(() => {});
    }

    const playerSelectors = ['#player', '.player', '[data-player]', 'video', 'iframe'];
    let playerElement = null;
    
    for (const selector of playerSelectors) {
      try {
        playerElement = await page.locator(selector).first();
        if (await playerElement.isVisible({ timeout: 2000 })) {
          break;
        }
      } catch (error) {
        continue;
      }
    }

    if (playerElement) {
      try {
        const [response] = await Promise.all([
          page.waitForResponse(
            res => res.ok() && res.url().includes('.m3u8'),
            { timeout: 15000 }
          ),
          playerElement.click({ force: true })
        ]);
        
        console.log(response.url());
        await browser.close();
        process.exit(0);
      } catch (error) {
        console.error("Errore durante il click sul player o attesa della risposta:", error.message);
      }
    }

    if (responses.length > 0) {
      console.log(responses[0]);
      await browser.close();
      process.exit(0);
    } else {
      await browser.close();
      process.exit(1);
    }
  } catch (error) {
    console.error("Errore generale in Playwright:", error.message);
    await browser.close();
    process.exit(1);
  }
})();
