// Steps file for scripts/pw_record.py (one take = one file, e.g. screen/steps/S03_ADD.js).
//   python3 scripts/pw_record.py take <profile> screen/steps/S03_ADD.js screen/raw/S03_ADD.webm
// Plain JS inside a Playwright page function (no import/require). In scope: page, wait, go, settle, hover, click,
// clickAt, type, press, scroll, smooth, dismiss, rest. target = a Playwright locator (getByRole / getByText /
// getByLabel / getByPlaceholder; snapshot refs like e62 change between loads) or [x, y] in page CSS px.

const START = [760, 420];                  // where the (hidden) pointer rests when the recording starts

// NOT recorded: bring the page to the take's start state and let late-loading UI settle.
async function setup() {
  await go('/app/contacts');                                        // a path resolves against the current origin
  await settle(page.getByRole('button', { name: 'New contact' }), 2000);
  await dismiss(page.getByRole('button', { name: 'Accept all' }));  // only if a banner is there
}

// Recorded: one call per action the narration will name, in script order. Wait for what proves the page is ready
// (a dialog, a heading, a count), never for fixed seconds alone.
async function take() {
  await hover(page.getByRole('heading', { name: 'Contacts' }), { settle: 1200 });
  await click(page.getByRole('button', { name: 'New contact' }), { ready: page.getByRole('dialog'), after: 1200 });
  const dlg = page.getByRole('dialog');
  await type(dlg.getByLabel('First name'), 'Jamie', { delay: 90 });
  await type(dlg.getByLabel('Email'), 'jamie@example.com', { delay: 60 });
  await click(dlg.getByRole('combobox', { name: 'Lifecycle stage' }), { after: 800 });
  await click(page.getByRole('option', { name: 'Lead' }), { after: 900 });
  await click(dlg.getByRole('button', { name: 'Save', exact: true }), { ready: page.getByText('Jamie').first(), after: 2000 });
  await hover(page.getByText('Jamie').first(), { settle: 1500 });
  // inside an iframe:  const F = page.frameLocator('iframe[src*="calendar"]'); await click(F.getByText('New'));
  // a covered button:  await clickAt(page.getByRole('button', { name: 'Save' }), 24);   // 24 px from its left edge
  // readable scroll:   await smooth(400, [640, 420]);
}
