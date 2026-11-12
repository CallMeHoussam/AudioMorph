document.addEventListener('DOMContentLoaded', () => {

  // 1. Tab Switching
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.dataset.tab;

      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      document.getElementById(`tab-${tabId}`).classList.add('active');
      hideStatus();
    });
  });

  // 2. Setup Drop Zones for Files
  setupDropZone('drop-converter', 'file-converter', 'name-converter');
  setupDropZone('drop-cutter', 'file-cutter', 'name-cutter');
  setupDropZone('drop-subtitles', 'file-subtitles', 'name-subtitles');
  setupDropZone('drop-vocals', 'file-vocals', 'name-vocals');

  function setupDropZone(zoneId, inputId, nameId) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);
    const nameLabel = document.getElementById(nameId);

    if (!zone || !input) return;

    zone.addEventListener('click', () => input.click());

    input.addEventListener('change', () => {
      if (input.files.length > 0) {
        nameLabel.textContent = `Selected: ${input.files[0].name}`;
        nameLabel.style.color = '#06b6d4';
      }
    });

    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
      zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        input.files = e.dataTransfer.files;
        nameLabel.textContent = `Selected: ${input.files[0].name}`;
        nameLabel.style.color = '#06b6d4';
      }
    });
  }

  // 3. Status helpers
  const statusCard = document.getElementById('status-card');
  const statusText = document.getElementById('status-text');
  const progressBar = document.getElementById('progress-bar');
  const spinner = document.getElementById('status-spinner');

  function showStatus(message, isIndeterminate = true) {
    statusCard.classList.remove('hidden');
    statusText.textContent = message;
    statusText.style.color = '#f3f4f6';
    spinner.style.display = 'block';
    if (isIndeterminate) {
      progressBar.style.width = '100%';
      progressBar.style.animation = 'pulse 1.5s infinite';
    } else {
      progressBar.style.width = '0%';
      progressBar.style.animation = 'none';
    }
  }

  function hideStatus() {
    statusCard.classList.add('hidden');
  }

  function showError(msg) {
    statusCard.classList.remove('hidden');
    statusText.textContent = `Error: ${msg}`;
    statusText.style.color = '#ef4444';
    spinner.style.display = 'none';
    progressBar.style.width = '100%';
    progressBar.style.background = '#ef4444';
  }

  async function handleFormSubmit(formId, endpoint, buttonId) {
    const form = document.getElementById(formId);
    const btn = document.getElementById(buttonId);

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(form);

      btn.disabled = true;
      showStatus('Processing media... please wait.');

      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          body: formData
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({ detail: 'Processing failed' }));
          throw new Error(errData.detail || 'Server processing error');
        }

        // Get filename from Content-Disposition header if available
        let filename = 'downloaded_media';
        const disposition = response.headers.get('Content-Disposition');
        if (disposition && disposition.includes('filename=')) {
          const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
          if (matches != null && matches[1]) {
            filename = matches[1].replace(/['"]/g, '');
          }
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);

        showStatus('Processing Complete! Download started.', false);
        progressBar.style.width = '100%';
        progressBar.style.background = 'linear-gradient(135deg, #10b981 0%, #06b6d4 100%)';
        spinner.style.display = 'none';
      } catch (err) {
        showError(err.message);
      } finally {
        btn.disabled = false;
      }
    });
  }

  // Bind Form Submissions
  handleFormSubmit('form-converter', '/api/convert', 'btn-converter');
  handleFormSubmit('form-downloader', '/api/download', 'btn-downloader');
  handleFormSubmit('form-cutter', '/api/cut', 'btn-cutter');
  handleFormSubmit('form-subtitles', '/api/subtitles', 'btn-subtitles');
  handleFormSubmit('form-vocals', '/api/vocal-isolation', 'btn-vocals');

});
