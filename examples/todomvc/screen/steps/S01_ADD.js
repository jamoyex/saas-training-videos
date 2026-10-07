// S01_ADD: add three to-dos, tick one off. Public demo app, nothing to log into, safe to re-shoot.
//   python3 scripts/pw_record.py open todomvc https://demo.playwright.dev/todomvc
//   python3 scripts/pw_record.py take todomvc examples/todomvc/screen/steps/S01_ADD.js examples/todomvc/screen/raw/S01_ADD.webm
const START = [640, 420];
const input = () => page.getByPlaceholder('What needs to be done?');

async function setup() {
  await go('https://demo.playwright.dev/todomvc/#/');
  await page.evaluate(() => localStorage.clear());       // start from an empty list every take
  await page.reload();
  await settle(input(), 1200);
}

async function take() {
  await hover(page.getByRole('heading', { name: 'todos' }), { settle: 1200 });
  await type(input(), 'Book the venue', { delay: 90, after: 400 });
  await press('Enter', { after: 1100 });
  await type(null, 'Send the invites', { delay: 90, after: 400 });
  await press('Enter', { after: 1100 });
  await type(null, 'Order the cake', { delay: 90, after: 400 });
  await press('Enter', { after: 1400 });
  await click(page.getByTestId('todo-item').filter({ hasText: 'Book the venue' }).getByRole('checkbox'), { after: 1400 });
  await hover(page.getByText(/items? left/), { settle: 1400 });
  await click(page.getByRole('link', { name: 'Completed' }), { after: 1500 });
  await click(page.getByRole('link', { name: 'All' }), { after: 1500 });
}
