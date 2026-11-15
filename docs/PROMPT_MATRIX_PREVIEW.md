# Preview prompt variations without generating images

`POST /api/prompt/matrix/preview` previews a small, deterministic prefix of a prompt matrix. It does not call an image provider or enqueue generation jobs.

Example request:

```json
{"prompt":"a {red|blue} {cat|dog}","limit":3}
```

Example response:

```json
{
  "original":"a {red|blue} {cat|dog}",
  "combinations":["a red cat","a red dog","a blue cat"],
  "count":3,
  "total_combinations":"4",
  "truncated":true
}
```

- `limit` defaults to 16 and must be an integer from 1 through 50.
- Prompts are limited to 2,000 characters, matching the existing matrix API.
- `total_combinations` is an exact decimal string, not a JSON number, so JavaScript clients do not round large counts.
- `truncated` means more variations exist than the preview shows. It does not indicate lost generation results.
- Results are the first combinations in existing matrix order, not a random or representative sample.
- Malformed matrix syntax returns 400; invalid request bounds are rejected by the request schema.
- The existing `/api/prompt/matrix` endpoint retains its full-expansion ceiling. Previewing a large matrix does not grant permission to generate all its combinations.

The creative studio at `/lumira` includes **Explore text variations** under **Your Vision**. It previews up to six variations. **Use variation** only replaces the draft prompt and returns focus to the text field; it does not submit a commission or start generation. The existing generation controls remain separate.
