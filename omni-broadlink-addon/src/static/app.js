document.addEventListener('DOMContentLoaded', () => {
  let discoveredHubs = {};
  let savedRemotes = {};
  let capturedCommands = {};
  let customButtonsList = [];
  let learningBtnKey = null;
  let pollIntervalRef = null;

  const hubsGrid = document.getElementById('hubs-grid');
  const remotesGrid = document.getElementById('remotes-grid');
  const hubCountBadge = document.getElementById('hub-count-badge');
  const remoteCountBadge = document.getElementById('remote-count-badge');

  const btnScan = document.getElementById('btn-scan');
  const btnOpenWizard = document.getElementById('btn-open-wizard');
  const btnCloseWizard = document.getElementById('btn-close-wizard');
  const btnCancelWizard = document.getElementById('btn-cancel-wizard');
  const btnSaveRemote = document.getElementById('btn-save-remote');
  const btnCancelLearning = document.getElementById('btn-cancel-learning');

  const wizardModal = document.getElementById('wizard-modal');
  const wizRemoteName = document.getElementById('wiz-remote-name');
  const wizSelectHub = document.getElementById('wiz-select-hub');
  const wizRemoteType = document.getElementById('wiz-remote-type');
  const wizDeviceType = document.getElementById('wiz-device-type');
  const wizButtonsGrid = document.getElementById('wizard-buttons-grid');
  const wizCustomBtnName = document.getElementById('wiz-custom-btn-name');
  const btnAddCustomButton = document.getElementById('btn-add-custom-button');

  const statusBanner = document.getElementById('learning-status-banner');
  const bannerPhase = document.getElementById('banner-phase');
  const bannerHint = document.getElementById('banner-hint');

  async function fetchStatus(forceScan = false) {
    try {
      const res = await fetch(`api/broadlink/devices?force=${forceScan}`);
      if (res.ok) {
        const data = await res.json();
        discoveredHubs = data.discovered || {};
        savedRemotes = data.remotes || {};
        renderHubs();
        renderRemotes();
        populateHubDropdown();
      }
    } catch (err) {
      console.error("Error al obtener estado Broadlink:", err);
    }
  }

  function renderHubs() {
    const ips = Object.keys(discoveredHubs);
    hubCountBadge.textContent = `${ips.length} Dispositivo(s)`;

    if (ips.length === 0) {
      hubsGrid.innerHTML = `
        <div class="empty-state glass-card">
          <span class="empty-icon">📡</span>
          <p>No se encontraron concentradores Broadlink en la red local.</p>
        </div>
      `;
      return;
    }

    hubsGrid.innerHTML = ips.map(ip => {
      const hub = discoveredHubs[ip];
      return `
        <div class="hub-card glass-card">
          <div class="hub-icon">📡</div>
          <div class="hub-info">
            <h3>${hub.name || 'Broadlink Hub'}</h3>
            <p class="hub-meta">IP: ${hub.ip} | MAC: ${hub.mac}</p>
            <p class="hub-meta">Modelo: ${hub.model}</p>
          </div>
        </div>
      `;
    }).join('');
  }

  function populateHubDropdown() {
    const ips = Object.keys(discoveredHubs);
    wizSelectHub.innerHTML = ips.length === 0 
      ? '<option value="">No hay hubs detectados (ingrese IP manual)</option>'
      : ips.map(ip => `<option value="${ip}">${discoveredHubs[ip].name} (${ip})</option>`).join('');
  }

  function renderRemotes() {
    const names = Object.keys(savedRemotes);
    remoteCountBadge.textContent = `${names.length} Dispositivo(s)`;

    if (names.length === 0) {
      remotesGrid.innerHTML = `
        <div class="empty-state glass-card">
          <span class="empty-icon">🎮</span>
          <p>No se han registrado controles remotos todavía.</p>
          <button class="btn btn-primary btn-sm" id="btn-create-first">+ Crear primer control</button>
        </div>
      `;
      const btnFirst = document.getElementById('btn-create-first');
      if (btnFirst) btnFirst.addEventListener('click', openWizard);
      return;
    }

    remotesGrid.innerHTML = names.map(name => {
      const remote = savedRemotes[name];
      const btns = Object.keys(remote.commands || {});
      const slug = name.toLowerCase().replace(/ /g, '_');
      const entityId = `${remote.domain || 'switch'}.omni_broadlink_${slug}`;

      return `
        <div class="remote-card glass-card">
          <div class="remote-card-header">
            <div class="remote-card-title">
              <h3>${remote.name}</h3>
              <span class="remote-tag">${remote.type} • ${remote.domain || 'switch'}</span>
              <p class="remote-entity-id">HA Entity: <code>${entityId}</code></p>
            </div>
            <button class="btn btn-danger btn-sm btn-delete-remote" data-name="${remote.name}">🗑️</button>
          </div>
          <div class="remote-buttons-grid">
            ${btns.map(btnKey => `
              <button class="remote-btn-action" data-remote="${remote.name}" data-key="${btnKey}">
                <span>${btnKey}</span>
              </button>
            `).join('')}
          </div>
        </div>
      `;
    }).join('');

    document.querySelectorAll('.remote-btn-action').forEach(btn => {
      btn.addEventListener('click', () => {
        const remoteName = btn.getAttribute('data-remote');
        const btnKey = btn.getAttribute('data-key');
        sendBroadlinkCommand(remoteName, btnKey, btn);
      });
    });

    document.querySelectorAll('.btn-delete-remote').forEach(btn => {
      btn.addEventListener('click', () => {
        const remoteName = btn.getAttribute('data-name');
        deleteRemote(remoteName);
      });
    });
  }

  async function sendBroadlinkCommand(remoteName, btnKey, buttonElem) {
    buttonElem.classList.add('sending');
    try {
      const res = await fetch('api/broadlink/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: remoteName, command: btnKey })
      });
      if (res.ok) {
        buttonElem.classList.remove('sending');
        buttonElem.classList.add('success');
      } else {
        buttonElem.classList.remove('sending');
      }
    } catch (err) {
      console.error("Error enviando comando:", err);
      buttonElem.classList.remove('sending');
    } finally {
      setTimeout(() => {
        buttonElem.classList.remove('success');
      }, 1000);
    }
  }

  async function deleteRemote(remoteName) {
    if (!confirm(`¿Desea eliminar el control remoto "${remoteName}"?`)) return;
    try {
      const res = await fetch('api/broadlink/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: remoteName })
      });
      if (res.ok) {
        fetchStatus();
      }
    } catch (err) {
      console.error("Error al eliminar control:", err);
    }
  }

  function openWizard() {
    wizardModal.classList.remove('hidden');
    wizRemoteName.value = '';
    wizCustomBtnName.value = '';
    capturedCommands = {};
    customButtonsList = [];
    learningBtnKey = null;
    renderWizardButtons();
    updateSaveButtonState();
  }

  function closeWizard() {
    cancelLearning();
    wizardModal.classList.add('hidden');
  }

  function renderWizardButtons() {
    if (customButtonsList.length === 0) {
      wizButtonsGrid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 24px; text-align: center; color: var(--text-muted); font-size: 0.9rem;">
          ✏️ Escriba el nombre del botón arriba y haga clic en <strong>+ Añadir Botón</strong> para agregarlo al control.
        </div>
      `;
      return;
    }

    wizButtonsGrid.innerHTML = customButtonsList.map(btn => {
      const isCaptured = !!capturedCommands[btn.key];
      return `
        <div class="wiz-btn-item ${isCaptured ? 'captured' : ''}">
          <span style="font-size:1.2rem;">${btn.icon || '⚡'}</span>
          <span class="wiz-btn-label">${btn.label}</span>
          <button class="btn ${isCaptured ? 'btn-secondary' : 'btn-primary'} btn-sm btn-learn-key" data-key="${btn.key}">
            ${isCaptured ? '✔ Capturado' : '⚡ Capturar'}
          </button>
        </div>
      `;
    }).join('');

    document.querySelectorAll('.btn-learn-key').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.getAttribute('data-key');
        startLearning(key);
      });
    });
  }

  function addCustomButton() {
    const rawName = wizCustomBtnName.value.trim();
    if (!rawName) return;
    const key = rawName.toLowerCase().replace(/ /g, '_').replace(/[^a-z0-9_]/g, '');
    if (!key) return;

    if (!customButtonsList.some(b => b.key === key)) {
      customButtonsList.push({ key: key, label: rawName, icon: '⚡' });
      wizCustomBtnName.value = '';
      renderWizardButtons();
    }
  }

  async function startLearning(btnKey) {
    const ip = wizSelectHub.value;
    if (!ip) {
      alert("Por favor seleccione un Broadlink Hub de la lista.");
      return;
    }

    learningBtnKey = btnKey;
    const mode = wizRemoteType.value.toLowerCase();
    showStatusBanner("Iniciando modo aprendizaje...", "Espere a que el Broadlink entre en modo escucha");

    try {
      const res = await fetch('api/broadlink/learn/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip, mode })
      });
      if (res.ok) {
        pollLearningStatus();
      } else {
        hideStatusBanner();
        alert("Error al iniciar modo de aprendizaje en Broadlink.");
      }
    } catch (err) {
      console.error(err);
      hideStatusBanner();
    }
  }

  function pollLearningStatus() {
    if (pollIntervalRef) clearInterval(pollIntervalRef);

    let attempts = 0;
    pollIntervalRef = setInterval(async () => {
      attempts++;
      if (attempts > 90) {
        clearInterval(pollIntervalRef);
        hideStatusBanner();
        alert("Tiempo de espera agotado sin recibir señal.");
        return;
      }

      try {
        const res = await fetch('api/broadlink/learn/status');
        if (res.ok) {
          const state = await res.json();
          updateBannerState(state);

          if (state.status === 'captured' && state.captured_data) {
            clearInterval(pollIntervalRef);
            capturedCommands[learningBtnKey] = state.captured_data;
            hideStatusBanner();
            renderWizardButtons();
            updateSaveButtonState();
          } else if (state.status === 'error') {
            clearInterval(pollIntervalRef);
            hideStatusBanner();
            alert(`Error en aprendizaje: ${state.error_msg || state.last_error}`);
          }
        }
      } catch (err) {
        console.error(err);
      }
    }, 750);
  }

  async function cancelLearning() {
    if (pollIntervalRef) clearInterval(pollIntervalRef);
    const ip = wizSelectHub.value;
    try {
      await fetch('api/broadlink/learn/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip })
      });
    } catch (e) {}
    hideStatusBanner();
  }

  function updateBannerState(state) {
    if (state.phase === 'ir_waiting') {
      showStatusBanner("Modo IR Activo", "Apunte el control remoto al Broadlink y presione el botón una vez corta.");
    } else if (state.phase === 'rf_sweep') {
      showStatusBanner("Barrido de Frecuencia RF (Paso 1)", "Mantenga PRESIONADO el botón del control físico hasta que se bloquee la frecuencia.");
    } else if (state.phase === 'rf_frequency_found' || state.phase === 'rf_packet_waiting') {
      const freqText = state.frequency ? ` (${state.frequency} MHz)` : '';
      showStatusBanner(`Esperando Paquete RF${freqText} (Paso 2)`, "Frecuencia detectada. Presione el botón del control una vez más para capturar.");
    }
  }

  function showStatusBanner(title, hint) {
    statusBanner.classList.remove('hidden');
    bannerPhase.textContent = title;
    bannerHint.textContent = hint;
  }

  function hideStatusBanner() {
    statusBanner.classList.add('hidden');
  }

  function updateSaveButtonState() {
    const hasName = wizRemoteName.value.trim().length > 0;
    const hasHub = wizSelectHub.value.length > 0;
    const hasCommands = Object.keys(capturedCommands).length > 0;
    btnSaveRemote.disabled = !(hasName && hasHub && hasCommands);
  }

  async function saveRemote() {
    const name = wizRemoteName.value.trim();
    const ip = wizSelectHub.value;
    const type = wizRemoteType.value.startsWith('RF') ? 'RF' : 'IR';
    const deviceType = wizDeviceType.value;
    const domain = deviceType === 'tv' || deviceType === 'audio' || deviceType === 'projector' ? 'media_player' : (deviceType === 'climate' ? 'climate' : (deviceType === 'light' ? 'light' : 'switch'));

    try {
      btnSaveRemote.disabled = true;
      const res = await fetch('api/broadlink/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          ip,
          type,
          commands: capturedCommands,
          domain,
          device_type: deviceType
        })
      });

      if (res.ok) {
        closeWizard();
        fetchStatus();
      } else {
        alert("Error al guardar el control remoto.");
        btnSaveRemote.disabled = false;
      }
    } catch (err) {
      console.error(err);
      alert("Error al guardar el control remoto.");
      btnSaveRemote.disabled = false;
    }
  }

  btnScan.addEventListener('click', () => fetchStatus(true));
  btnOpenWizard.addEventListener('click', openWizard);
  btnCloseWizard.addEventListener('click', closeWizard);
  btnCancelWizard.addEventListener('click', closeWizard);
  btnCancelLearning.addEventListener('click', cancelLearning);
  btnAddCustomButton.addEventListener('click', addCustomButton);
  wizCustomBtnName.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addCustomButton();
    }
  });
  wizDeviceType.addEventListener('change', renderWizardButtons);
  wizRemoteName.addEventListener('input', updateSaveButtonState);
  wizSelectHub.addEventListener('change', updateSaveButtonState);
  btnSaveRemote.addEventListener('click', saveRemote);

  fetchStatus();
});
