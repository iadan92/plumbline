-- subscription billing (generic example)
CREATE TABLE public.customers (
  customer_id   BIGINT PRIMARY KEY,
  email         VARCHAR(255) NOT NULL,
  created_at    TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE TABLE plans (
  plan_id  INT NOT NULL,
  name     TEXT,
  price    NUMERIC(10,2),
  CONSTRAINT plans_pk PRIMARY KEY (plan_id)
);
CREATE TABLE IF NOT EXISTS subscriptions (
  subscription_id BIGINT NOT NULL,
  customer_id     BIGINT NOT NULL REFERENCES customers (customer_id),
  plan_id         INT NOT NULL,
  started_on      DATE,
  PRIMARY KEY (subscription_id),
  FOREIGN KEY (plan_id) REFERENCES plans(plan_id)
);
CREATE TABLE invoices (
  invoice_id      BIGINT PRIMARY KEY,
  subscription_id BIGINT,
  total           NUMERIC(12,2),
  status          VARCHAR(20) CHECK (status IN ('open','paid','void'))
);
ALTER TABLE ONLY invoices ADD CONSTRAINT invoices_sub_fk FOREIGN KEY (subscription_id) REFERENCES subscriptions(subscription_id);
CREATE TABLE payments (
  payment_id  BIGINT PRIMARY KEY,
  invoice_id  BIGINT REFERENCES invoices(invoice_id),
  paid_amount NUMERIC(12,2)
);
CREATE INDEX idx_inv ON invoices(status);
CREATE VIEW v AS SELECT 1;
