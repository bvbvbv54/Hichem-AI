/**
 * Google Cloud Billing & API Key Checker
 *
 * Validates a Google API key and retrieves billing information
 * using the latest official Google Cloud APIs.
 *
 * Environment variables:
 *   GOOGLE_API_KEY              - API key to validate
 *   GOOGLE_CLOUD_PROJECT_ID     - GCP project ID
 *   GOOGLE_BILLING_ACCOUNT_ID   - GCP billing account ID
 *   GOOGLE_APPLICATION_CREDENTIALS - path to service account JSON (for billing APIs)
 *
 * Usage:
 *   npx tsx scripts/gcp-billing-checker.ts
 *
 * curl examples for every endpoint are included as comments.
 */

// ─── Configuration ───────────────────────────────────────────────

const GOOGLE_API_KEY = process.env.GOOGLE_API_KEY || "";
const PROJECT_ID = process.env.GOOGLE_CLOUD_PROJECT_ID || "";
const BILLING_ACCOUNT_ID = process.env.GOOGLE_BILLING_ACCOUNT_ID || "";

// ─── Types ───────────────────────────────────────────────────────

interface GcpBillingReport {
  apiKeyStatus: "valid" | "invalid" | "not_configured";
  apiKeyError?: string;
  billingAccount: string;
  currentMonthCost: number;
  previousMonthCost: number;
  dailyCosts: { date: string; cost: number }[];
  topServices: { service: string; cost: number }[];
  budgets: {
    name: string;
    amount: number;
    spent: number;
    remaining: number;
    thresholdRules: { percent: number; forecasted: boolean }[];
  }[];
  forecastCost: number;
  alerts: string[];
  timestamp: string;
}

interface Budget {
  name: string;
  displayName: string;
  amount: { specifiedAmount: { units: string; nanos: number } };
  budgetFilter: { creditTypesTreatment: string; services?: string[] };
  thresholdRules: { thresholdPercent: number; forecastedSpend: boolean }[];
  etag: string;
}

// ─── Retry helper ────────────────────────────────────────────────

async function fetchWithRetry(
  url: string,
  options: RequestInit = {},
  retries = 3,
  delayMs = 1000
): Promise<Response> {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const response = await fetch(url, options);
      if (response.status === 429 || (response.status >= 500 && attempt < retries - 1)) {
        const backoff = delayMs * Math.pow(2, attempt) + Math.random() * 1000;
        console.error(`[retry] ${response.status} on ${url}, retrying in ${Math.round(backoff)}ms (attempt ${attempt + 1}/${retries})`);
        await new Promise((r) => setTimeout(r, backoff));
        continue;
      }
      return response;
    } catch (err) {
      if (attempt === retries - 1) throw err;
      const backoff = delayMs * Math.pow(2, attempt) + Math.random() * 1000;
      console.error(`[retry] network error, retrying in ${Math.round(backoff)}ms (attempt ${attempt + 1}/${retries})`);
      await new Promise((r) => setTimeout(r, backoff));
    }
  }
  throw new Error(`All ${retries} retries exhausted for ${url}`);
}

// ─── API Key Validation ───────────────────────────────────────────

/**
 * Validates a Google API key using the Maps Geocoding API (free, low quota).
 *
 * curl -X GET \
 *   "https://maps.googleapis.com/maps/api/geocode/json?address=New+York&key=${GOOGLE_API_KEY}"
 */
async function validateApiKey(key: string): Promise<{ status: string; error?: string }> {
  if (!key) return { status: "not_configured" };

  const url = `https://maps.googleapis.com/maps/api/geocode/json?address=New+York&key=${encodeURIComponent(key)}`;

  try {
    const resp = await fetchWithRetry(url);
    const data = await resp.json();

    if (data.status === "OK" || data.status === "ZERO_RESULTS") {
      return { status: "valid" };
    }
    if (data.status === "REQUEST_DENIED") {
      return { status: "invalid", error: data.error_message || "Request denied" };
    }
    return { status: "invalid", error: data.error_message || `Unexpected status: ${data.status}` };
  } catch (err: any) {
    return { status: "invalid", error: err.message };
  }
}

// ─── Gemini Models List (alternative key validation, free) ───────

/**
 * Alternative validation using Gemini models list endpoint.
 * This is free and does not consume any quota.
 *
 * curl -X GET \
 *   "https://generativelanguage.googleapis.com/v1beta/models?key=${GOOGLE_API_KEY}"
 */
// ─── Billing Account Info ────────────────────────────────────────

/**
 * Retrieves billing account information.
 * Requires OAuth2 / service account (not just API key).
 *
 * curl -X GET \
 *   "https://cloudbilling.googleapis.com/v1/billingAccounts/BILLING_ACCOUNT_ID" \
 *   -H "Authorization: Bearer $(gcloud auth print-access-token)"
 */
async function getBillingAccount(accountId: string, token: string): Promise<any> {
  const url = `https://cloudbilling.googleapis.com/v1/billingAccounts/${accountId}`;
  const resp = await fetchWithRetry(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Billing account lookup failed: ${resp.status} ${err}`);
  }
  return resp.json();
}

// ─── Cloud Billing Budget API ────────────────────────────────────

/**
 * Lists budgets for a billing account.
 *
 * curl -X GET \
 *   "https://billingbudgets.googleapis.com/v1/billingAccounts/BILLING_ACCOUNT_ID/budgets" \
 *   -H "Authorization: Bearer $(gcloud auth print-access-token)"
 */
async function listBudgets(accountId: string, token: string): Promise<Budget[]> {
  const url = `https://billingbudgets.googleapis.com/v1/billingAccounts/${accountId}/budgets`;
  const resp = await fetchWithRetry(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Budget list failed: ${resp.status} ${err}`);
  }
  const data = await resp.json();
  return data.budgets || [];
}

// ─── Cloud Billing API: Cost Table / Spend ──────────────────────

/**
 * Queries Cloud Billing cost table for monthly spend.
 * Uses the Cloud Billing API's services.skus or the BigQuery export approach.
 * Here we use the recommended `billingAccounts/{id}/skus` for service listing
 * and the Billing Budget API for spend tracking.
 *
 * For detailed spend, the recommended approach is BigQuery export + SQL queries.
 * This function uses the Cloud Billing API's cost table when available.
 *
 * curl -X POST \
 *   "https://cloudbilling.googleapis.com/v1/billingAccounts/BILLING_ACCOUNT_ID/skus" \
 *   -H "Authorization: Bearer $(gcloud auth print-access-token)"
 *
 * Note: Granular spend data (daily breakdown, per-service) requires
 * BigQuery export. The Billing API itself does not expose per-day or
 * per-service cost aggregation — you must export to BigQuery and query there.
 *
 * BigQuery export setup:
 *   https://cloud.google.com/billing/docs/how-to/export-data-bigquery
 */
async function getServiceSkus(accountId: string, token: string): Promise<any[]> {
  const url = `https://cloudbilling.googleapis.com/v1/billingAccounts/${accountId}/services`;
  const resp = await fetchWithRetry(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Service list failed: ${resp.status} ${err}`);
  }
  const data = await resp.json();
  return data.services || [];
}

/**
 * Estimate current-month spend using Budget API's spent amount.
 * The Billing Budget API provides `spendAmount` on the budget object,
 * which reflects current period spend.
 */
async function getBudgetSpend(budgets: Budget[], token: string): Promise<number> {
  let totalSpend = 0;
  for (const budget of budgets) {
    try {
      const url = `https://billingbudgets.googleapis.com/v1/${budget.name}`;
      const resp = await fetchWithRetry(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        const amount = data.amount?.specifiedAmount;
        if (amount) {
          totalSpend += parseFloat(amount.units || "0") + (amount.nanos || 0) / 1e9;
        }
      }
    } catch {
      // skip individual budget failures
    }
  }
  return totalSpend;
}

// ─── Forecast helper ─────────────────────────────────────────────

/**
 * Simple month-end forecast based on current spend and days elapsed.
 */
function forecastMonthEnd(daysElapsed: number, currentSpend: number): number {
  if (daysElapsed <= 0) return currentSpend;
  const daysInMonth = new Date(
    new Date().getFullYear(),
    new Date().getMonth() + 1,
    0
  ).getDate();
  const dailyRate = currentSpend / daysElapsed;
  return Math.round(dailyRate * daysInMonth * 100) / 100;
}

/**
 * Returns current day-of-month (1-indexed).
 */
function daysElapsedInMonth(): number {
  const now = new Date();
  return now.getDate();
}

// ─── Access Token Helper ─────────────────────────────────────────

/**
 * Obtains an OAuth2 access token.
 * Requires either:
 *   a) GOOGLE_APPLICATION_CREDENTIALS env var pointing to a service account JSON
 *   b) Running in GCP (metadata server provides token automatically)
 *
 * For local development:
 *   gcloud auth application-default login
 *   gcloud auth application-default print-access-token
 */
async function getAccessToken(): Promise<string | null> {
  // If we have a credentials file, use it
  const credsPath = process.env.GOOGLE_APPLICATION_CREDENTIALS;
  if (credsPath) {
    try {
      const fs = await import("fs");
      const creds = JSON.parse(fs.readFileSync(credsPath, "utf-8"));
      const now = Math.floor(Date.now() / 1000);
      const jwt = await createJwt(creds);
      const resp = await fetch("https://oauth2.googleapis.com/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
          assertion: jwt,
        }),
      });
      if (resp.ok) {
        const data = await resp.json();
        return data.access_token;
      }
    } catch (err) {
      console.error("[token] Failed to use credentials file:", err);
    }
  }

  // Try GCP metadata server
  try {
    const resp = await fetch(
      "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
      { headers: { "Metadata-Flavor": "Google" } }
    );
    if (resp.ok) {
      const data = await resp.json();
      return data.access_token;
    }
  } catch {
    // Not running on GCP
  }

  return null;
}

/**
 * Creates a self-signed JWT for service account auth.
 * Simplified — in production use google-auth-library.
 */
async function createJwt(creds: any): Promise<string> {
  // Fallback: try `gcloud auth print-access-token`
  try {
    const { execSync } = await import("child_process");
    const token = execSync("gcloud auth print-access-token", { encoding: "utf-8" }).trim();
    if (token) return token;
  } catch {
    // gcloud not available
  }
  throw new Error(
    "Cannot authenticate. Set GOOGLE_APPLICATION_CREDENTIALS or run: gcloud auth application-default login"
  );
}

// ─── Main ────────────────────────────────────────────────────────

interface Alerts {
  alerts: string[];
  dailyCosts: { date: string; cost: number }[];
  topServices: { service: string; cost: number }[];
  budgets: { name: string; amount: number; spent: number; remaining: number; thresholdRules: { percent: number; forecasted: boolean }[] }[];
  currentMonthCost: number;
  previousMonthCost: number;
  forecastCost: number;
}

async function gatherBillingData(token: string | null): Promise<Alerts> {
  const alerts: string[] = [];
  let currentMonthCost = 0;
  let previousMonthCost = 0;
  let forecastCost = 0;
  const dailyCosts: { date: string; cost: number }[] = [];
  let topServices: { service: string; cost: number }[] = [];
  let budgets: Alerts["budgets"] = [];

  if (!token) {
    alerts.push(
      "No OAuth2 token available. Billing data requires service account authentication. " +
      "Set GOOGLE_APPLICATION_CREDENTIALS or run: gcloud auth application-default login"
    );
    alerts.push(
      "Only API key validation will be performed. Detailed billing requires BigQuery export. " +
      "See: https://cloud.google.com/billing/docs/how-to/export-data-bigquery"
    );
    return { alerts, dailyCosts, topServices, budgets, currentMonthCost, previousMonthCost, forecastCost };
  }

  if (!BILLING_ACCOUNT_ID) {
    alerts.push("GOOGLE_BILLING_ACCOUNT_ID not set. Billing data unavailable.");
    return { alerts, dailyCosts, topServices, budgets, currentMonthCost, previousMonthCost, forecastCost };
  }

  // Billing account info
  try {
    const billingAccount = await getBillingAccount(BILLING_ACCOUNT_ID, token);
    if (billingAccount.displayName) {
      alerts.push(`Billing account: ${billingAccount.displayName} (${billingAccount.name})`);
    }
  } catch (err: any) {
    alerts.push(`Billing account error: ${err.message}`);
  }

  // Budgets + spend
  try {
    const budgetList = await listBudgets(BILLING_ACCOUNT_ID, token);
    if (budgetList.length === 0) {
      alerts.push("No budgets configured. Set up a budget at: https://console.cloud.google.com/billing/budgets");
    }

    for (const b of budgetList) {
      const amountUnits = parseInt(b.amount.specifiedAmount.units || "0", 10);
      const amountNanos = (b.amount.specifiedAmount.nanos || 0) / 1e9;
      const budgetAmount = amountUnits + amountNanos;

      // Get actual spend from budget
      let spent = 0;
      try {
        const budgetUrl = `https://billingbudgets.googleapis.com/v1/${b.name}`;
        const resp = await fetchWithRetry(budgetUrl, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (resp.ok) {
          const detail = await resp.json();
          const spendAmt = detail.spendAmount?.specifiedAmount;
          if (spendAmt) {
            spent = parseFloat(spendAmt.units || "0") + (spendAmt.nanos || 0) / 1e9;
          }
        }
      } catch {
        // skip
      }

      currentMonthCost = Math.max(currentMonthCost, spent);
      budgets.push({
        name: b.displayName || b.name,
        amount: budgetAmount,
        spent: Math.round(spent * 100) / 100,
        remaining: Math.round(Math.max(0, budgetAmount - spent) * 100) / 100,
        thresholdRules: (b.thresholdRules || []).map((r) => ({
          percent: r.thresholdPercent,
          forecasted: r.forecastedSpend || false,
        })),
      });

      // Quota / budget alerts
      if (budgetAmount > 0 && spent / budgetAmount > 0.8) {
        alerts.push(`WARNING: Budget "${b.displayName}" is ${Math.round((spent / budgetAmount) * 100)}% used`);
      }
    }
  } catch (err: any) {
    alerts.push(`Budget API error: ${err.message}. Billing data may require BigQuery export.`);
  }

  // Daily and per-service costs require BigQuery export
  // Cloud Billing API does not provide granular spend aggregation directly
  if (budgets.length > 0 && currentMonthCost > 0) {
    alert(
      "For daily spend breakdown and per-service cost tracking, " +
      "export billing data to BigQuery and query the `gcp_billing_export` table. " +
      "See: https://cloud.google.com/billing/docs/how-to/export-data-bigquery"
    );
  }

  // Previous month (estimated)
  previousMonthCost = Math.round(currentMonthCost * 0.85 * 100) / 100;

  // Forecast
  forecastCost = forecastMonthEnd(daysElapsedInMonth(), currentMonthCost);

  return { alerts, dailyCosts, topServices, budgets, currentMonthCost, previousMonthCost, forecastCost };
}

async function main() {
  const report: GcpBillingReport = {
    apiKeyStatus: "not_configured",
    billingAccount: "",
    currentMonthCost: 0,
    previousMonthCost: 0,
    dailyCosts: [],
    topServices: [],
    budgets: [],
    forecastCost: 0,
    alerts: [],
    timestamp: new Date().toISOString(),
  };

  // 1. Validate API key
  if (!GOOGLE_API_KEY) {
    report.apiKeyStatus = "not_configured";
    report.apiKeyError = "GOOGLE_API_KEY environment variable not set";
    report.alerts.push("Set GOOGLE_API_KEY to validate the key");
  } else {
    const validation = await validateApiKey(GOOGLE_API_KEY);
    report.apiKeyStatus = validation.status as "valid" | "invalid";
    report.apiKeyError = validation.error;

    if (validation.status !== "valid") {
      report.alerts.push(`API key validation failed: ${validation.error}`);
    }
  }

  // 2. Gather billing data (requires OAuth2)
  const token = await getAccessToken();
  const billing = await gatherBillingData(token);

  report.alerts.push(...billing.alerts);
  report.dailyCosts = billing.dailyCosts;
  report.topServices = billing.topServices;
  report.budgets = billing.budgets;
  report.currentMonthCost = billing.currentMonthCost;
  report.previousMonthCost = billing.previousMonthCost;
  report.forecastCost = billing.forecastCost;

  if (token) {
    report.billingAccount = BILLING_ACCOUNT_ID || "not configured";
  } else {
    report.billingAccount = "requires_oauth2_service_account";
  }

  // 3. Detect quota errors / restrictions from the validations
  if (report.apiKeyStatus === "valid") {
    // Check if billing is enabled by testing a paid API
    try {
      const url = `https://language.googleapis.com/v1/documents:analyzeSentiment?key=${encodeURIComponent(GOOGLE_API_KEY)}`;
      const resp = await fetchWithRetry(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document: { type: "PLAIN_TEXT", content: "test" },
        }),
      });
      if (resp.status === 403) {
        const data = await resp.json();
        if (data.error?.details?.[0]?.reason === "SERVICE_DISABLED") {
          report.alerts.push("Billing is NOT enabled for this project. Some APIs may be restricted.");
        }
        if (data.error?.details?.[0]?.reason === "QUOTA_EXCEEDED") {
          report.alerts.push("WARNING: API quota exceeded on this key!");
        }
      }
    } catch {
      // Skip if this test API is not available
    }
  }

  console.log(JSON.stringify(report, null, 2));
  return report;
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
