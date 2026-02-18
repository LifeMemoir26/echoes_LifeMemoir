# Frontend (Memoir Reader)

## Run

```bash
cd frontend
npm install
npm run dev
```

默认接口地址：`http://localhost:8000/api/v1`

可通过环境变量覆盖：

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

## Contract Assumptions

- 统一响应信封：`status/data/errors`
- memoir 接口：`POST /generate/memoir`
- 成功字段：`memoir/length/generated_at/trace_id`
- 错误字段：`error_code/error_message/retryable/trace_id`

## Verification Commands

```bash
npm run typecheck
npm run test
npm run check:contract
```
