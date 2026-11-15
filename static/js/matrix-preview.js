/* Text-only exploration. Never calls generation or submits the commission form. */
(() => {
  const prompt = document.getElementById('request-prompt');
  const button = document.getElementById('matrix-preview-button');
  const status = document.getElementById('matrix-preview-status');
  const results = document.getElementById('matrix-preview-results');
  if (!prompt || !button || !status || !results) return;
  let version = 0;
  prompt.addEventListener('input', () => {
    version += 1;
    results.replaceChildren();
    status.textContent = '';
  });
  button.addEventListener('click', async () => {
    const text = prompt.value.trim();
    results.replaceChildren();
    if (!text) {
      status.textContent = 'Describe your vision first, using options such as {red|blue}.';
      prompt.focus();
      return;
    }
    const current = ++version;
    button.disabled = true;
    status.textContent = 'Previewing text variations. No images are being generated.';
    try {
      const response = await fetch('/api/prompt/matrix/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: text, limit: 6 }),
      });
      const data = await response.json();
      if (current !== version) return;
      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Preview unavailable. Check your options or try again later.');
      }
      if (!Array.isArray(data.combinations) || data.combinations.length > 6 ||
          !data.combinations.every(value => typeof value === 'string' && value.length <= 2000) ||
          typeof data.total_combinations !== 'string' || !/^\d{1,1000}$/.test(data.total_combinations)) {
        throw new Error('Preview unavailable. Please try again.');
      }
      status.textContent = `Showing ${data.combinations.length} of ${data.total_combinations} text variations. No images generated.`;
      data.combinations.forEach((text, index) => {
        const item = document.createElement('li');
        const sample = document.createElement('p');
        sample.textContent = text;
        const use = document.createElement('button');
        use.type = 'button';
        use.textContent = `Use variation ${index + 1}`;
        use.addEventListener('click', () => {
          prompt.value = text;
          prompt.dispatchEvent(new Event('input', { bubbles: true }));
          status.textContent = 'Variation added to Your Vision. Nothing has been generated or submitted.';
          prompt.focus();
        });
        item.append(sample, use);
        results.append(item);
      });
    } catch (error) {
      if (current === version) status.textContent = error instanceof Error ? error.message : 'Preview unavailable. Please try again.';
    } finally {
      button.disabled = false;
    }
  });
})();
