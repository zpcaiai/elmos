CREATE OR REPLACE FUNCTION runtime.allocate_fence(p_work_item_id uuid)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE v_token bigint;
BEGIN
    INSERT INTO runtime.work_item_fence_counters(work_item_id, next_token)
    VALUES(p_work_item_id, 1)
    ON CONFLICT(work_item_id)
    DO UPDATE SET next_token = runtime.work_item_fence_counters.next_token + 1
    RETURNING next_token INTO v_token;

    RETURN v_token;
END;
$$;
