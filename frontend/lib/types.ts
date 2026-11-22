// Mirrors the FastAPI response schemas (backend/app/schemas.py).

export type Campaign = { id: number; name: string; niche: string; location: string; offer: string | null; created_at: string };

export type CampaignStats = {
  leads: number; with_email: number; scored: number; drafts: number; approved: number; sent: number; opted_out: number;
  to_enrich: number; to_score: number; to_draft: number; to_review: number; to_send: number;
};

export type Lead = {
  id: number; campaign_id: number; name: string; website: string | null; phone: string | null; address: string | null;
  email: string | null; rating: number | null; review_count: number | null; source: string; status: string;
  score: number | null; score_reason: string | null;
};
export type LeadList = { total: number; items: Lead[] };

export type Draft = {
  id: number; lead_id: number; lead_name: string; to_email: string; subject: string; body: string; status: string; preview: string;
};

export type SentEmail = { id: number; draft_id: number; to_email: string; subject: string; status: string; error: string | null; message_id: string | null };

export type Mailbox = {
  id: number; from_email: string; from_name: string | null; smtp_host: string; smtp_port: number; smtp_username: string;
  security: string; daily_limit: number; status: string; paused_reason: string | null; sent_today: number;
};

export type Profile = { sender_name: string | null; company_name: string | null; postal_address: string | null; complete: boolean; missing: string[] };
export type Me = { email: string; workspace_name: string; profile_complete: boolean; profile_missing: string[] };
export type Suppression = { id: number; email: string; reason: string };

export type ImportResult = { added: number; skipped_duplicates: number; skipped_suppressed: number; skipped_invalid: number };
export type EnrichResult = { checked: number; found: number; not_found: number; suppressed: number };
export type ScoreSummary = { scored: number; failed: number; rate_limited: boolean; remaining: number; last_error: string | null };
export type DraftSummary = { generated: number; failed: number; rate_limited: boolean; remaining: number; last_error: string | null };
export type WouldSend = { draft_id: number; to_email: string; subject: string };
export type SendSummary = {
  dry_run: boolean; sent: number; rejected: number; skipped_opted_out: number; quota_remaining: number;
  mailbox_paused: boolean; stopped_reason: string | null; would_send: WouldSend[];
};
