-- Contact rate limit lookup: leads per IP hash in the last hour. Spec section 6.

CREATE INDEX idx_leads_ip_hash_created ON leads (ip_hash, created_at);
