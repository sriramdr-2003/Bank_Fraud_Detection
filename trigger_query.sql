---------------------------------------------------------------
-- ORDER INVALID AMOUNT TRIGGER
---------------------------------------------------------------

CREATE OR ALTER TRIGGER trg_check_order_amt
ON orders
INSTEAD OF INSERT
AS
BEGIN
    SET NOCOUNT ON;

    -- If ANY invalid order exists → log & STOP
    IF EXISTS (
        SELECT 1
        FROM inserted
        WHERE order_amount <= 0
    )
    BEGIN
        INSERT INTO notification_queue (
            account_id,
            message,
            created_at,
            event_type,
            processed
        )
        SELECT
            NULL,
            'Order amount must be greater than zero',
            GETDATE(),
            'INVALID_ORDER_AMOUNT',
            0
        FROM inserted
        WHERE order_amount <= 0;

        RETURN;  
    END;

    -- Only valid rows reach here
    INSERT INTO orders (customer_name, order_amount)
    SELECT
        customer_name,
        order_amount
    FROM inserted;
END;
GO



---------------------------------------------------------------
-- TRANSACTION EXCEED TRIGGER
---------------------------------------------------------------

CREATE OR ALTER TRIGGER trg_enforce_daily_limit
ON transactions
INSTEAD OF INSERT
AS
BEGIN
    SET NOCOUNT ON;

    --  Reject transactions exceeding daily limit
    IF EXISTS (
        SELECT 1
        FROM inserted i
        JOIN accounts a ON a.account_id = i.account_id
        WHERE
            (
                SELECT ISNULL(SUM(t.amount), 0)
                FROM transactions t
                WHERE t.account_id = i.account_id
                  AND CAST(t.txn_timestamp AS DATE) = CAST(i.txn_timestamp AS DATE)
            ) + i.amount > a.daily_txn_limit
    )
    BEGIN
        -- Log notification
        INSERT INTO notification_queue (
            account_id,
            event_type,
            message,
            created_at,
            processed
        )
        SELECT
            i.account_id,
            'DAILY_LIMIT_EXCEEDED',
            'Daily transaction limit exceeded',
            GETDATE(),
            0
        FROM inserted i;

        RETURN;  
    END;

    --  Insert ALL columns
    INSERT INTO transactions (
        txn_id,
        account_id,
        amount,
        txn_type,
        merchant_country,
        device_id,
        txn_timestamp
    )
    SELECT
        txn_id,
        account_id,
        amount,
        txn_type,
        merchant_country,
        device_id,
        txn_timestamp
    FROM inserted;
END;
GO


---------------------------------------------------------------
-- RISK SCORE TRIGGER
---------------------------------------------------------------


CREATE OR ALTER TRIGGER trg_risk_score_monitor
ON transactions
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;

    /* -------------------------------------------------
       Rule 1: More than 5 transactions in last 10 minutes
    ------------------------------------------------- */
    ;WITH txn_count AS (
        SELECT
            t.account_id,
            COUNT(*) AS txn_cnt
        FROM transactions t
        WHERE t.txn_timestamp >= DATEADD(MINUTE, -10, GETDATE())
        GROUP BY t.account_id
    )
    UPDATE a
    SET a.risk_score = ISNULL(a.risk_score, 0) + 20
    FROM accounts a
    JOIN txn_count tc
        ON a.account_id = tc.account_id
    WHERE tc.txn_cnt > 2;

	/* -------------------------------------------------
       Rule 2: Freeze accounts with risk_score >= 60
    ------------------------------------------------- */
    UPDATE a
    SET a.account_status = 'FROZEN'
    FROM accounts a
    WHERE a.risk_score >= 60
      AND a.account_id IN (SELECT DISTINCT account_id FROM inserted);
    /* -------------------------------------------------
       Rule 3: Risk score >= 60 → FRAUD ALERT
    ------------------------------------------------- */
    INSERT INTO notification_queue (
        account_id,
        event_type,
        message,
        created_at,
        processed
    )
    SELECT
        a.account_id,
        'HIGH_RISK_ACCOUNT',
        'Risk score exceeded 60 due to frequent transactions',
        GETDATE(),
        0
    FROM accounts a
    WHERE a.risk_score >= 60
      AND a.account_id IN (SELECT DISTINCT account_id FROM inserted);
END;
GO


