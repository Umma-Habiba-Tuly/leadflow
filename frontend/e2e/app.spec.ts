import { expect, test, type Browser, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const PASSWORD = "e2e-password-123";
let counter = 0;
const uniqueEmail = () => `e2e-${Date.now()}-${++counter}@example.com`;

/** In dev a screenshot/click before React hydrates can race it; on a production build, waiting for idle is enough. */
async function open(page: Page, url: string) {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
}

async function register(page: Page, company = "E2E Studio") {
  await open(page, "/login");
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Company name").fill(company);
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/campaigns");
}

async function createCampaign(page: Page, name = "Austin dentists") {
  await page.getByRole("button", { name: "New campaign" }).click();
  await page.getByLabel("Campaign name").fill(name);
  await page.getByLabel("Kind of business").fill("dental clinic");
  await page.getByLabel("Where").fill("Austin, TX");
  await page.getByLabel("What are you offering them?").fill("Website redesign and local SEO");
  await page.getByRole("button", { name: "Create campaign" }).click();
  await page.waitForURL(/\/campaigns\/\d+$/);
}

function csvFile(rows: string[]): string {
  const file = path.join(__dirname, ".tmp", `leads-${Date.now()}-${++counter}.csv`);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, ["name,website,email,rating,review_count,address", ...rows].join("\n"));
  return file;
}

test.describe("navigation (docs-style sidebar, like ai-sdk.dev)", () => {
  test("a new campaign shows up in the sidebar right away and is marked as the current page", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await register(page);
    await createCampaign(page, "Sidebar test campaign");
    const sidebar = page.getByRole("navigation", { name: "Main" });
    await expect(sidebar).toBeVisible();
    // No reload: the layout that renders this list has to be refreshed after the campaign is created.
    await expect(sidebar.getByRole("link", { name: "Sidebar test campaign" })).toHaveAttribute("aria-current", "page");
    await expect(sidebar.getByRole("link", { name: "All campaigns" })).not.toHaveAttribute("aria-current", "page");
    await sidebar.getByRole("link", { name: "Settings" }).click();
    await page.waitForURL("**/settings");
    await expect(sidebar.getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page");
  });

  test("on a phone the sidebar is replaced by links in the header", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await register(page);
    await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
    const header = page.getByRole("navigation", { name: "Primary" });
    await expect(header.getByRole("link", { name: "Campaigns" })).toBeVisible();
    await header.getByRole("link", { name: "Settings" }).click();
    await page.waitForURL("**/settings");
  });

  test("header controls never overlap or fall off the screen on a phone", async ({ page }) => {
    // Found by looking at a real 390px screenshot: the nav and "Sign out" collided and the button wrapped.
    await page.setViewportSize({ width: 390, height: 844 });
    await register(page);
    const boxes = await page.evaluate(() => {
      const rect = (el: Element | null) => { const r = el!.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; };
      const links = [...document.querySelectorAll('nav[aria-label="Primary"] a')].map(rect);
      const signOut = rect([...document.querySelectorAll("header button")].find((b) => /sign out/i.test(b.textContent ?? "")) ?? null);
      return { lastLink: links[links.length - 1], signOut, width: window.innerWidth };
    });
    expect(boxes.signOut.right, "Sign out stays on screen").toBeLessThanOrEqual(boxes.width);
    expect(boxes.lastLink.right, "nav and Sign out do not overlap").toBeLessThanOrEqual(boxes.signOut.left);
    expect(boxes.signOut.bottom - boxes.signOut.top, "Sign out is a single line").toBeLessThan(48);
  });

  test("only your own campaigns are listed", async ({ page, browser }: { page: Page; browser: Browser }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await register(page, "Company A");
    await createCampaign(page, "Secret campaign of A");
    const other = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
    await register(other, "Company B");
    await expect(other.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Secret campaign of A" })).toHaveCount(0);
    await other.context().close();
  });
});

test.describe("layout", () => {
  // The most common way a layout breaks on a small screen is sideways scrolling.
  for (const [name, width, height] of [["desktop", 1280, 800], ["laptop", 1024, 700], ["phone", 390, 844]] as const) {
    test(`login and the dashboard never scroll sideways (${name})`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await open(page, "/login");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "login").toBe(true);
      await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

      await register(page);
      await createCampaign(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "campaign page").toBe(true);
    });
  }
});

test.describe("landing page", () => {
  test("a visitor sees the pitch, and Get started opens the sign-up form", async ({ page }) => {
    await open(page, "/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Find leads. Score them. Send emails");
    await page.getByRole("main").getByRole("link", { name: "Get started" }).click();
    await page.waitForURL("**/login?mode=register");
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
    await expect(page.getByLabel("Company name")).toBeVisible();
  });

  test("Sign in opens the sign-in form, not sign-up", async ({ page }) => {
    await open(page, "/");
    await page.getByRole("banner").getByRole("link", { name: "Sign in" }).click();
    await page.waitForURL("**/login");
    await expect(page.getByRole("heading", { name: "Sign in to LeadFlow" })).toBeVisible();
  });

  test("someone who is already signed in goes straight to the app", async ({ page }) => {
    await register(page);
    await page.goto("/");
    await expect(page).toHaveURL(/\/campaigns$/);
  });

  test("the step tabs switch the explanation and the preview, and say the data is made up", async ({ page }) => {
    await open(page, "/");
    const tabs = page.getByRole("tablist", { name: "How LeadFlow works" });
    await expect(tabs.getByRole("tab", { name: /Find/ })).toHaveAttribute("aria-selected", "true");
    await tabs.getByRole("tab", { name: /Score/ }).click();
    await expect(tabs.getByRole("tab", { name: /Score/ })).toHaveAttribute("aria-selected", "true");
    const panel = page.getByRole("tabpanel");
    await expect(panel).toContainText("Every lead is ranked against your offer.");
    await expect(panel).toContainText("example, made-up data");
    await tabs.getByRole("tab", { name: /Review/ }).click();
    await expect(panel).toContainText("cannot be removed");
  });

  for (const [name, width, height] of [["desktop", 1280, 800], ["laptop", 1024, 700], ["phone", 390, 844]] as const) {
    test(`never scrolls sideways (${name})`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await open(page, "/");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expect(page.getByRole("main").getByRole("link", { name: "Get started" })).toBeVisible();
    });
  }
});

test.describe("signing in", () => {
  test("every private page sends a visitor to the login page", async ({ page }) => {
    for (const url of ["/campaigns", "/settings", "/campaigns/1"]) {
      await page.goto(url);
      await expect(page).toHaveURL(/\/login$/);
    }
  });

  test("a wrong password shows a clear message and does not sign in", async ({ page }) => {
    await open(page, "/login");
    await page.getByLabel("Email").fill("nobody@example.com");
    await page.getByLabel("Password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    // Next.js also keeps a hidden role="alert" route announcer, so match ours by its text.
    await expect(page.getByRole("alert").filter({ hasText: "Wrong email or password" })).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("register, see the profile reminder, sign out, and be locked out again", async ({ page }) => {
    await register(page);
    await expect(page.getByText("Add your sender details before you can write or send emails")).toBeVisible();
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL("**/login");
    await page.goto("/campaigns");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("the session cookie cannot be read by page scripts", async ({ page, context }) => {
    await register(page);
    expect(await page.evaluate(() => document.cookie)).not.toContain("lf_token");
    const cookie = (await context.cookies()).find((c) => c.name === "lf_token");
    expect(cookie?.httpOnly).toBe(true);
    expect(cookie?.sameSite).toBe("Lax");
  });
});

test.describe("the proxy is not an open door", () => {
  test("refuses paths the dashboard never uses, even when signed in", async ({ page }) => {
    await register(page);
    for (const p of ["docs", "openapi.json", "u/sometoken", "auth/login", "health"]) {
      const res = await page.request.get(`/api/proxy/${p}`);
      expect(res.status(), p).toBe(404);
    }
  });

  test("refuses state-changing calls that do not come from our own pages", async ({ page }) => {
    await register(page);
    const evil = await page.request.post("/api/proxy/campaigns", {
      headers: { Origin: "https://evil.example", "Content-Type": "application/json" },
      data: { name: "x", niche: "y", location: "z" },
    });
    expect(evil.status()).toBe(403);
    const noOrigin = await page.request.post("/api/proxy/campaigns", { data: { name: "x", niche: "y", location: "z" } });
    expect(noOrigin.status()).toBe(403);
  });

  test("needs a session", async ({ request }) => {
    expect((await request.get("/api/proxy/auth/me")).status()).toBe(401);
  });
});

test.describe("working with a campaign", () => {
  test("create a campaign, import a CSV, and a hostile website is shown as plain text, not a link", async ({ page }) => {
    let dialogOpened = false;
    page.on("dialog", async (d) => { dialogOpened = true; await d.dismiss(); });

    await register(page);
    await createCampaign(page);
    await expect(page.getByRole("heading", { name: "Austin dentists" })).toBeVisible();

    const file = csvFile([
      "Bright Smile Dental,https://brightsmile.example,hello@brightsmile.example,3.6,210,12 Oak St",
      "Evil Dental,javascript:alert(document.cookie),evil@evil.example,4.0,10,1 Bad St",
      "Plain Dental,plain.example,info@plain.example,4.2,40,2 Plain St",
    ]);
    await page.locator('input[type="file"]').setInputFiles(file);
    await expect(page.getByText("Added 3 leads.")).toBeVisible();

    await expect(page.getByRole("link", { name: "brightsmile.example" })).toHaveAttribute("href", "https://brightsmile.example/");
    await expect(page.getByRole("link", { name: "plain.example" })).toBeVisible(); // a bare domain still works
    await expect(page.locator('a[href^="javascript:" i]')).toHaveCount(0);
    await expect(page.getByText("javascript:alert(document.cookie)")).toBeVisible(); // shown as text only
    expect(dialogOpened).toBe(false);

    // Importing the same file again adds nothing new.
    await page.locator('input[type="file"]').setInputFiles(file);
    await expect(page.getByText(/Added 0 leads\. Skipped: 3 duplicates\./)).toBeVisible();
  });

  test("the dark button always marks the step to do next", async ({ page }) => {
    await register(page);
    await createCampaign(page);
    const next = page.locator("[data-next]");

    // nothing yet: bring in some leads
    await expect(next).toHaveCount(1);
    await expect(next).toContainText("Leads");
    await expect(next.getByRole("button", { name: "Import CSV" })).toBeVisible();

    // leads with an email: scoring comes next
    await page.locator('input[type="file"]').setInputFiles(csvFile(["Alpha Dental,https://alpha.example,hello@alpha.example,4.1,50,1 Main St"]));
    await expect(page.getByText("Added 1 lead.")).toBeVisible();
    await expect(next).toContainText("Score");
    await expect(next.getByRole("button", { name: "Score leads" })).toBeEnabled();

    // a lead with a website but no email: finding that email comes first
    await page.locator('input[type="file"]').setInputFiles(csvFile(["Beta Dental,https://beta.example,,3.9,20,2 Main St"]));
    await expect(page.getByText("Added 1 lead.")).toBeVisible();
    await expect(next).toContainText("Find emails");
  });

  test("writing emails is blocked until the sender details exist", async ({ page }) => {
    await register(page);
    await createCampaign(page);
    await expect(page.getByRole("button", { name: "Write emails" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Send…" })).toBeDisabled();
  });

  test("another company cannot open this campaign", async ({ page, browser }: { page: Page; browser: Browser }) => {
    await register(page, "Company A");
    await createCampaign(page);
    const url = page.url();

    const otherContext = await browser.newContext();
    const other = await otherContext.newPage();
    await register(other, "Company B");
    const response = await other.goto(url);
    expect(response?.status()).toBe(404);
    await otherContext.close();
  });
});

test.describe("settings", () => {
  test("saving the sender details removes the reminder", async ({ page }) => {
    await register(page);
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");
    await page.getByLabel("Your name").fill("Sam Rivera");
    await page.getByLabel("Company").fill("Rivera Web Studio");
    await page.getByLabel("Postal address").fill("100 Congress Ave, Austin, TX 78701");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText(/Saved\. You can now write and send emails\./)).toBeVisible();
    await page.goto("/campaigns");
    await expect(page.getByText("Add your sender details before you can write or send emails")).toHaveCount(0);
  });

  test("a mailbox pointing at the server itself is refused (SSRF guard)", async ({ page }) => {
    await register(page);
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");
    await page.getByLabel("From email").fill("sam@rivera.example");
    await page.getByLabel("SMTP server").fill("127.0.0.1");
    await page.getByLabel("Port").fill("587");
    await page.getByLabel("Username").fill("sam@rivera.example");
    await page.locator('input[name="smtp_password"]').fill("secret-app-password");
    await page.getByRole("button", { name: "Connect mailbox" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "SMTP host must be a public mail server" })).toBeVisible();
    await expect(page.getByText("No mailbox connected")).toBeVisible();
  });
});
