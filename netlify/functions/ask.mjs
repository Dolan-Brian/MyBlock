/*
 * MyBlock's agent, running as a Netlify Function.
 *
 * This is a JavaScript port of agent.py and the five tools_*.py files.
 * Same system prompt, same tool descriptions, same model, same 5 tool
 * call limit, same queries against NYC Open Data. The goal of the port is
 * that the eval results in EVAL_SET.md still describe how this behaves.
 *
 * Differences from the Python version, all on purpose:
 * - Text from the model is escaped before it goes into a SoQL query
 *   (single quotes doubled). On a public website, a visitor's question
 *   shapes the tool inputs, so this keeps a crafted question from
 *   rewriting a query.
 * - Number inputs are clamped to sane ranges, so a tool call can't ask
 *   the city for years of data at once.
 * - Tool calls in the same round run at the same time instead of one by
 *   one, and the whole run stops at a deadline, to stay inside Netlify's
 *   60 second limit.
 * - The answer comes back with a list of the tools called and a summary
 *   of each result's source, freshness and coverage, so the page can
 *   show them.
 *
 * Secrets: ANTHROPIC_API_KEY and SOCRATA_APP_TOKEN are read from Netlify
 * environment variables. They are never sent to the browser.
 */

const MODEL = "claude-haiku-4-5-20251001";
const MAX_TOOL_CALLS = 5;
const MAX_QUESTION_CHARS = 300;
const DEADLINE_MS = 50_000; // stop before Netlify's 60 second limit
const SOCRATA_TIMEOUT_MS = 15_000;

// ---------- system prompt: copied from agent.py (version 3) ----------

const SYSTEM_PROMPT = `You are a research assistant with access to real NYC civic data tools. Follow these rules strictly:

1. State only facts that came from a tool's returned data in this conversation. Never state a specific address, zip code, distance, or landmark detail unless it appeared in a tool result. If you want to add general knowledge, label it clearly as such, separate from the data.

2. Every tool here reports data at the borough level, not at the neighborhood or address level. When a question names a neighborhood or landmark, call the relevant tool for its borough and use the returned data - do not ask permission first. If individual records in the result include an address, you may use those to narrow your answer to what's actually relevant. State plainly, as part of your answer, that the underlying data is borough-wide.

3. An empty or zero result is missing data, not a finding. Never describe it as calm, quiet, safe, or good. Say plainly that no data was available for that query and time window.

4. A single number or a single time snapshot is not a trend. Only describe something as improving, worsening, or changing over time if the data itself came from a tool built to compare two time periods.

5. If you are not confident a tool understood the location as intended (for example, a neighborhood name rather than a borough), say so explicitly rather than presenting the result as if it matched the user's question exactly.

6. If a question asks about a specific time (a particular hour, "right now", "lately"), and a tool returns data with its own timestamp, state that timestamp and whether it could plausibly cover the time asked about. Never call data "real-time" or "current" without giving the actual timestamp. If the two don't clearly match, say so explicitly rather than answering as if they do.

7. Always attempt the most useful available tool call before answering. Disclosing a limitation is not a substitute for using the data you have access to. Only decline to look something up, or ask a clarifying question first, when no available tool could plausibly help at all.`;

// ---------- tool schemas: copied from tool_schemas.py ----------

const BOROUGH_DESC =
  "The NYC borough to search (e.g., 'Brooklyn', 'Queens', 'Manhattan', 'Bronx', 'Staten Island').";
const BOROUGH_DESC_CHECK =
  "The NYC borough to check (e.g., 'Brooklyn', 'Queens', 'Manhattan', 'Bronx', 'Staten Island').";

const ALL_TOOLS = [
  {
    name: "get_311_complaints",
    description:
      "Search NYC's official 311 service request records for a specific " +
      "borough. Use this to answer questions about noise complaints, " +
      "illegal parking, sanitation issues, or other quality-of-life " +
      "complaints filed by residents. The complaint_type parameter should " +
      "match how NYC categorizes complaints (e.g., 'Noise - Residential', " +
      "'Illegal Parking', 'Dirty Conditions') - if unsure of the exact " +
      "category, a partial or best-guess term is still useful. Can filter " +
      "by how far back to search.",
    input_schema: {
      type: "object",
      properties: {
        location: { type: "string", description: BOROUGH_DESC },
        complaint_type: {
          type: "string",
          description:
            "The specific type of complaint to filter for, e.g. 'Noise - Residential'. Optional - omit to search all complaint types.",
        },
        time_period_days: {
          type: "integer",
          description: "How many days back to search. Defaults to 30 if not specified.",
        },
      },
      required: ["location"],
    },
  },
  {
    name: "get_historical_trend",
    description:
      "Compare complaint volume in a NYC borough between the most recent " +
      "30 days and the same 30-day window from 6 months ago, to determine " +
      "whether an area is trending better or worse over time. Use this " +
      "when a question specifically asks about change over time, history, " +
      "or trends - not for questions about what's happening right now, " +
      "which get_311_complaints answers instead. The comparison window is " +
      "fixed at 6 months back, based on real testing - not adjustable.",
    input_schema: {
      type: "object",
      properties: {
        location: { type: "string", description: BOROUGH_DESC_CHECK },
        complaint_type: {
          type: "string",
          description:
            "The specific type of complaint to check the trend for, e.g. 'Noise - Residential'. Optional - omit to check overall complaint trends.",
        },
      },
      required: ["location"],
    },
  },
  {
    name: "get_parking_violations",
    description:
      "Check NYC's historical parking and camera violation records for a " +
      "specific borough. This is a large historical archive, not a " +
      "real-time feed - useful for gauging general enforcement patterns " +
      "and violation types in an area (e.g. whether alternate-side " +
      "parking or camera enforcement is common there), not for answering " +
      "questions about this week or 'lately' specifically. Also useful " +
      "as a proxy for related questions - such as whether an area has " +
      "heavy alternate-side parking enforcement, whether visitors or " +
      "non-residents frequently park there, or general patterns in how " +
      "strictly parking is enforced in a neighborhood.",
    input_schema: {
      type: "object",
      properties: {
        location: { type: "string", description: BOROUGH_DESC_CHECK },
      },
      required: ["location"],
    },
  },
  {
    name: "get_building_permits",
    description:
      "Check NYC Department of Buildings permit records for a specific " +
      "borough over a recent time window, showing construction, " +
      "renovation, or new development activity. Use this to answer " +
      "direct questions about construction or building work in an area, " +
      "and also as a proxy for related questions - such as whether a " +
      "neighborhood is actively changing or developing, whether there's " +
      "likely to be construction noise or disruption, or general signs " +
      "of real estate investment in the area.",
    input_schema: {
      type: "object",
      properties: {
        location: { type: "string", description: BOROUGH_DESC_CHECK },
        time_period_days: {
          type: "integer",
          description:
            "How many days back to search. Defaults to 180 if not specified, since permit activity is naturally less frequent than complaints.",
        },
      },
      required: ["location"],
    },
  },
  {
    name: "get_traffic_speeds",
    description:
      "Check real-time NYC traffic speed data for roads in a specific " +
      "borough. Use this to answer questions about current traffic " +
      "conditions, congestion, or how fast vehicles are moving in an " +
      "area right now. This is a live feed, but real testing has shown " +
      "individual boroughs can have several hours of lag between " +
      "updates - the most recent available data may not reflect the " +
      "exact current moment, so treat results as 'recent' rather than " +
      "'this instant.'",
    input_schema: {
      type: "object",
      properties: {
        location: { type: "string", description: BOROUGH_DESC_CHECK },
        hours_back: {
          type: "integer",
          description:
            "How many hours back to search for the most recent available data. Defaults to 24 if not specified, to reliably account for real feed lag.",
        },
      },
      required: ["location"],
    },
  },
];

// ---------- helpers ----------

// Escape text for a SoQL string literal: double any single quote.
const q = (s) => String(s).replace(/'/g, "''");

const clampInt = (v, def, min, max) => {
  const n = Number.isFinite(Number(v)) ? Math.round(Number(v)) : def;
  return Math.min(max, Math.max(min, n));
};

// Python's strftime("%Y-%m-%dT%H:%M:%S") in UTC
const isoNoMs = (d) => d.toISOString().slice(0, 19);

async function socrata(datasetId, params) {
  const url = new URL(`https://data.cityofnewyork.us/resource/${datasetId}.json`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
  const headers = {};
  if (process.env.SOCRATA_APP_TOKEN) headers["X-App-Token"] = process.env.SOCRATA_APP_TOKEN;
  const res = await fetch(url, { headers, signal: AbortSignal.timeout(SOCRATA_TIMEOUT_MS) });
  if (!res.ok) {
    console.log(`Socrata ${datasetId} error ${res.status}: ${(await res.text()).slice(0, 300)}`);
    return null;
  }
  return res.json();
}

// ---------- the five tools: ports of tools_*.py ----------

// tools_311.py
async function get_311_complaints({ location, complaint_type, time_period_days = 30 }) {
  const days = clampInt(time_period_days, 30, 1, 365);
  const since = isoNoMs(new Date(Date.now() - days * 86_400_000));
  const where = [`created_date > '${since}'`];
  if (location) where.push(`borough = '${q(String(location).toUpperCase())}'`);
  if (complaint_type) where.push(`complaint_type = '${q(complaint_type)}'`);
  const data = await socrata("erm2-nwe9", {
    $where: where.join(" AND "),
    $limit: 50,
    $order: "created_date DESC",
  });
  return data ?? [];
}

// tools_trend.py
async function get_historical_trend({ location, complaint_type, months_back = 6 }) {
  const months = clampInt(months_back, 6, 1, 24);
  const now = Date.now();
  const day = 86_400_000;
  const recentStart = isoNoMs(new Date(now - 30 * day));
  const compEnd = isoNoMs(new Date(now - months * 30 * day));
  const compStart = isoNoMs(new Date(now - (months * 30 + 30) * day));

  async function count(start, end) {
    const where = [`created_date > '${start}'`];
    if (end) where.push(`created_date < '${end}'`);
    if (location) where.push(`borough = '${q(String(location).toUpperCase())}'`);
    if (complaint_type) where.push(`complaint_type = '${q(complaint_type)}'`);
    const data = await socrata("erm2-nwe9", {
      $where: where.join(" AND "),
      $select: "count(*) as total",
    });
    if (data === null) return null;
    if (data.length && "total" in data[0]) return parseInt(data[0].total, 10);
    return 0;
  }

  const [recent, comparison] = await Promise.all([count(recentStart), count(compStart, compEnd)]);

  const result = {
    location,
    complaint_type: complaint_type || "all types",
    recent_window: `${recentStart} to now`,
    comparison_window: `${compStart} to ${compEnd}`,
    recent_30_day_count: recent,
    comparison_30_day_count_from_months_ago: comparison,
    months_back_compared: months,
  };
  if (recent !== null && comparison !== null && comparison > 0) {
    const pct = ((recent - comparison) / comparison) * 100;
    result.percent_change = Math.round(pct * 10) / 10;
    result.trend = pct > 10 ? "worsening" : pct < -10 ? "improving" : "stable";
  }
  return result;
}

// tools_parking.py
const BOROUGH_TO_COUNTY_CODE = {
  BROOKLYN: "K",
  BRONX: "BX",
  MANHATTAN: "NY",
  QUEENS: "Q",
  "STATEN ISLAND": "ST",
};

async function get_parking_violations({ location }) {
  const county = location ? BOROUGH_TO_COUNTY_CODE[String(location).toUpperCase()] : undefined;
  const params = { $limit: 1000 };
  if (county) params.$where = `county = '${county}'`;
  const data = await socrata("nc67-uf89", params);
  if (!data) return [];

  // issue_date is MM/DD/YYYY text. Parse it ourselves, drop malformed
  // records (e.g. "70/40/2000"), and sort newest first.
  const valid = [];
  for (const r of data) {
    const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(r.issue_date || "");
    if (!m) continue;
    const [, mm, dd, yyyy] = m.map(Number);
    const d = new Date(Date.UTC(yyyy, mm - 1, dd));
    // reject dates that roll over, like 13/40/2020
    if (d.getUTCMonth() !== mm - 1 || d.getUTCDate() !== dd) continue;
    valid.push([d.getTime(), r]);
  }
  valid.sort((a, b) => b[0] - a[0]);
  return valid.slice(0, 50).map(([, r]) => r);
}

// tools_permits.py
async function get_building_permits({ location, time_period_days = 180, limit = 50 }) {
  const days = clampInt(time_period_days, 180, 1, 730);
  const since = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10) + "T00:00:00.000";
  const where = [`issued_date > '${since}'`];
  if (location) where.push(`upper(borough) = '${q(String(location).toUpperCase())}'`);
  const data = await socrata("rbx6-tga4", {
    $where: where.join(" AND "),
    $limit: clampInt(limit, 50, 1, 50),
    $order: "issued_date DESC",
  });
  return data ?? [];
}

// tools_traffic.py
async function get_traffic_speeds({ location, hours_back = 24, limit = 50 }) {
  const hours = clampInt(hours_back, 24, 1, 72);
  const since = isoNoMs(new Date(Date.now() - hours * 3_600_000));
  const where = [`data_as_of > '${since}'`];
  if (location) where.push(`upper(borough) = '${q(String(location).toUpperCase())}'`);
  const data = await socrata("i4gi-tjb9", {
    $where: where.join(" AND "),
    $limit: clampInt(limit, 50, 1, 50),
    $order: "data_as_of DESC",
  });
  return data ?? [];
}

const TOOL_FUNCTIONS = {
  get_311_complaints,
  get_historical_trend,
  get_parking_violations,
  get_building_permits,
  get_traffic_speeds,
};

// ---------- what the page shows under each answer ----------

const SOURCES = {
  get_311_complaints: "NYC 311",
  get_historical_trend: "NYC 311",
  get_parking_violations: "NYC Dept. of Finance",
  get_building_permits: "NYC Dept. of Buildings",
  get_traffic_speeds: "NYC DOT traffic sensors",
};

const titleCase = (s) =>
  String(s || "").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

function fmtTime(iso) {
  // Socrata timestamps here are NYC local time without a zone marker.
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || "");
  if (!m) return null;
  const [, y, mo, d, h, mi] = m;
  const hour = Number(h);
  const ampm = hour >= 12 ? "PM" : "AM";
  const h12 = hour % 12 || 12;
  return `${Number(mo)}/${Number(d)}/${y}, ${h12}:${mi} ${ampm}`;
}

function newest(rows, field) {
  let best = null;
  for (const r of rows || []) if (r && r[field] && (!best || r[field] > best)) best = r[field];
  return best;
}

function describeCall(name, input, result) {
  const borough = titleCase(input.location);
  const call = { tool: name, label: "", asOf: "", stale: false };
  const n = Array.isArray(result) ? result.length : null;
  if (name === "get_311_complaints") {
    call.label = `311 complaints${input.complaint_type ? `: ${input.complaint_type}` : ""}, ${borough}, last ${clampInt(input.time_period_days, 30, 1, 365)} days (${n} records)`;
    call.asOf = n ? `Newest complaint ${fmtTime(newest(result, "created_date"))}` : "No records returned";
  } else if (name === "get_historical_trend") {
    call.label = `Complaint trend${input.complaint_type ? `: ${input.complaint_type}` : ""}, ${borough}, last 30 days vs. 6 months ago`;
    call.asOf = "Last 30 days, compared with 6 months ago";
  } else if (name === "get_parking_violations") {
    call.label = `Parking and camera violations, ${borough} (${n} records)`;
    call.asOf = "Historical archive, date unclear";
    call.stale = true;
  } else if (name === "get_building_permits") {
    call.label = `Building permits, ${borough}, last ${clampInt(input.time_period_days, 180, 1, 730)} days (${n} records)`;
    call.asOf = n ? `Newest permit ${fmtTime(newest(result, "issued_date"))?.split(",")[0]}` : "No records returned";
  } else if (name === "get_traffic_speeds") {
    call.label = `Traffic speeds, ${borough}, last ${clampInt(input.hours_back, 24, 1, 72)} hours (${n} readings)`;
    call.asOf = n ? `Newest reading ${fmtTime(newest(result, "data_as_of"))}` : "No readings returned";
    call.stale = true; // feed lag is real; always worth flagging
  }
  if (n === 0) call.stale = true;
  return { ...call, borough, source: SOURCES[name] };
}

// ---------- the agent loop: port of run_agent() in agent.py ----------

async function callClaude(messages, signal) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": process.env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 1500,
      system: SYSTEM_PROMPT,
      tools: ALL_TOOLS,
      tool_choice: { type: "auto" },
      messages,
    }),
    signal,
  });
  if (!res.ok) {
    const body = await res.text();
    console.log(`Anthropic error ${res.status}: ${body.slice(0, 500)}`);
    const err = new Error("model_error");
    err.status = res.status;
    throw err;
  }
  return res.json();
}

async function runAgent(question) {
  const deadline = AbortSignal.timeout(DEADLINE_MS);
  const messages = [{ role: "user", content: question }];
  const calls = [];
  let toolCallCount = 0;

  while (toolCallCount < MAX_TOOL_CALLS) {
    const response = await callClaude(messages, deadline);

    if (response.stop_reason !== "tool_use") {
      const answer = response.content
        .filter((b) => b.type === "text")
        .map((b) => b.text)
        .join("");
      return { answer, calls };
    }

    messages.push({ role: "assistant", content: response.content });

    const uses = response.content.filter((b) => b.type === "tool_use");
    toolCallCount += uses.length;

    const results = await Promise.all(
      uses.map(async (block) => {
        const fn = TOOL_FUNCTIONS[block.name];
        let result;
        if (!fn) {
          result = { error: `Unknown tool: ${block.name}` };
        } else {
          try {
            result = await fn(block.input || {});
          } catch (e) {
            result = { error: `Tool execution failed: ${e.message}` };
          }
        }
        return {
          call: fn ? describeCall(block.name, block.input || {}, result) : null,
          type: "tool_result",
          tool_use_id: block.id,
          content: JSON.stringify(result),
        };
      })
    );

    for (const r of results) if (r.call) calls.push(r.call);
    messages.push({ role: "user", content: results.map(({ call, ...r }) => r) });
  }

  return {
    answer:
      "I wasn't able to fully answer this within a reasonable number of tool calls. The question may be too broad, or may need to be more specific.",
    calls,
  };
}

// ---------- the web endpoint ----------

const json = (status, body) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });

export default async (req) => {
  if (req.method !== "POST") return json(405, { error: "Use POST." });
  if (!process.env.ANTHROPIC_API_KEY) {
    console.log("ANTHROPIC_API_KEY is not set");
    return json(500, { error: "MyBlock isn't set up on the server yet." });
  }

  let question = "";
  try {
    const body = await req.json();
    question = String(body?.question ?? "").trim();
  } catch {
    return json(400, { error: "Send a question as JSON." });
  }
  if (!question) return json(400, { error: "Type a question first." });
  if (question.length > MAX_QUESTION_CHARS) {
    return json(400, { error: `Keep questions under ${MAX_QUESTION_CHARS} characters.` });
  }

  try {
    const { answer, calls } = await runAgent(question);
    return json(200, { answer, calls });
  } catch (e) {
    if (e.name === "TimeoutError" || e.name === "AbortError") {
      return json(504, { error: "That took too long. Try a narrower question, like one borough and one topic." });
    }
    if (e.status === 429) {
      return json(429, { error: "MyBlock is getting too many questions right now. Try again in a minute." });
    }
    console.log(`Agent error: ${e.stack || e}`);
    return json(502, { error: "Something went wrong getting an answer. Try again." });
  }
};

export const config = { path: "/api/ask", method: "POST" };
