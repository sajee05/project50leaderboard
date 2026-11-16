// Cloudflare Worker (free plan): Telegram webhook -> GitHub repository_dispatch.
// Only messages / button presses from an admin that are known commands start a job; everything else is dropped here.
// Settings (Worker > Settings > Variables and Secrets):
//   BOT_TOKEN (secret)       the bot token, used only to send the quick "on it" reply
//   GH_TOKEN (secret)        fine-grained GitHub token for this repo only, permission "Contents: Read and write"
//   WEBHOOK_SECRET (secret)  any long random string; the same value goes into setWebhook's secret_token
//   REPO (variable)          sajee05/project50leaderboard
//   ADMIN_IDS (variable)     7574436736   (comma separated for several admins)
const COMMANDS = ["/daily", "/today", "/leaderboard", "/rerun", "/yesterday", "/weekly", "/monthly", "/show"];

export default {
  async fetch(req, env, ctx) {
    if (req.method !== "POST") return new Response("ok");
    if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    const upd = await req.json();
    const m = upd.message, cq = upd.callback_query;
    const sender = String(((m && m.from) || (cq && cq.from) || {}).id || "");
    const admins = (env.ADMIN_IDS || "7574436736").split(",").map((s) => s.trim());
    if (!admins.includes(sender)) return new Response("ok");           // strangers: silently ignored

    const text = (m && m.text) || (cq && cq.data) || "";
    const cmd = (text.split(/\s+/)[0] || "").split("@")[0].toLowerCase();
    if (!COMMANDS.includes(cmd) && !text.startsWith("rr:")) return new Response("ok");

    const gh = await fetch(`https://api.github.com/repos/${env.REPO}/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "leaderboard-worker",
      },
      body: JSON.stringify({ event_type: "telegram_update", client_payload: { update: upd } }),
    });

    const tg = (method, body) =>
      fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      });
    const note = gh.status === 204 ? "On it. The result arrives in a minute or two." : `Could not start the job (GitHub said ${gh.status}).`;
    if (cq) ctx.waitUntil(tg("answerCallbackQuery", { callback_query_id: cq.id, text: note }));
    else ctx.waitUntil(tg("sendMessage", { chat_id: m.chat.id, text: note }));
    return new Response("ok");
  },
};
