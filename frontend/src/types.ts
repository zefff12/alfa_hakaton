export type Role = "client" | "underwriter";

export interface Company {
  id: number;
  inn: string;
  ogrn: string | null;
  name: string;
  legal_form: string;
  okved: string | null;
  okved_name: string | null;
  industry: string | null;
  region: string | null;
  address: string | null;
  director: string | null;
  registered_at: string | null;
}

export interface User {
  id: number;
  login: string;
  role: Role;
  full_name: string;
  position: string | null;
  company: Company | null;
}

export interface Product {
  code: string;
  name: string;
  short: string;
  description: string;
  min_amount: number;
  max_amount: number;
  min_term: number;
  max_term: number;
  base_rate: number;
  min_business_age_months: number;
  collateral: "none" | "optional" | "required";
  purposes: string[];
  decision_time: string;
  revolving: boolean;
  required_documents: string[];
  highlights: string[];
}

export interface Catalog {
  products: Product[];
  purposes: { code: string; label: string }[];
  document_types: { code: string; label: string }[];
}

export interface Estimate {
  amount: number;
  rate: number;
  term_months: number;
  monthly_payment: number;
  total_interest: number;
  total_repayment: number;
  revolving: boolean;
  label?: string;
}

export interface OfferOption extends Estimate {
  id: string;
  label: string;
  product_code: string;
}

export interface Offer {
  product_code: string;
  product_name: string;
  options: OfferOption[];
  conditions: string[];
  valid_until: string;
}

export interface Factor {
  code: string;
  name: string;
  value: string;
  points: number;
  impact: "positive" | "negative" | "neutral";
  explanation: string;
  tip: string | null;
}

export interface TimelineEvent {
  id: number;
  from_status: string | null;
  to_status: string | null;
  to_label: string | null;
  actor_type: string;
  event_type: string;
  message: string;
  created_at: string;
  payload?: Record<string, unknown>;
}

export interface DocItem {
  id: number;
  doc_type: string;
  label: string;
  filename: string;
  size_bytes: number;
  status: string;
  created_at: string;
}

export interface Application {
  id: number;
  number: string;
  status: string;
  status_label: string;
  version: number;
  is_final: boolean;
  product_code: string | null;
  product_name: string | null;
  purpose: string | null;
  purpose_label: string | null;
  purpose_comment: string | null;
  amount: number | null;
  term_months: number | null;
  has_collateral: boolean;
  collateral_description: string | null;
  form_data: Record<string, any>;
  consents: Record<string, any>;
  precheck: any;
  estimate: Estimate | null;
  required_documents: { code: string; label: string }[];
  requested_documents: { code: string; label: string }[];
  offer: Offer | null;
  decision: any;
  signing: any;
  loan: any;
  documents: DocItem[];
  timeline: TimelineEvent[];
  track: { steps: string[]; current: number };
  alfik: { say?: string; eta?: string | null; todo?: string | null };
  allowed_transitions: string[];
  company: Company & { id: number };
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  decided_at: string | null;
  statement: any | null;
  // только в консоли банка
  data_check?: any;
  enrichment?: any;
  scoring?: any;
  applicant?: { id: number; full_name: string; position: string | null };
  summary?: any;
}

export interface ChatMsg {
  id: number;
  role: "user" | "assistant";
  content: string;
  source: string | null;
  meta: { actions?: { label: string; to: string; prefill?: string }[] } | null;
  created_at: string;
}

export const PROCESSING = ["SUBMITTED", "DATA_CHECK", "ENRICHMENT", "SCORING", "ISSUING"];
