package storage

import (
	"context"

	core "bankcore"
)

const insertTx = `
INSERT INTO transactions
(debit_account_id, credit_account_id, amount, currency, memo)
VALUES ($1,$2,$3,$4,$5)
RETURNING id, posted_at;
`

func InsertTransaction(ctx context.Context, in core.TransactionCreate) (*core.Transaction, error) {
	var out core.Transaction
	out.DebitAccountId = in.DebitAccountId
	out.CreditAccountId = in.CreditAccountId
	out.Amount = in.Amount
	out.Currency = in.Currency
	out.Memo = in.Memo

	if err := Pool.QueryRow(ctx, insertTx,
		in.DebitAccountId, in.CreditAccountId,
		in.Amount, in.Currency, in.Memo,
	).Scan(&out.Id, &out.PostedAt); err != nil {
		return nil, err
	}
	return &out, nil
}
