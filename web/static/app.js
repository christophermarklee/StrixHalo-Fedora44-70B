const serviceRoot = document.querySelector("#services");
const notice = document.querySelector("#notice");
const refreshButton = document.querySelector("#refresh");

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function stateLabel(state) {
  return state.replaceAll("_", " ");
}

function card(service) {
  const running = service.state === "running";
  const state = escapeHtml(service.state);
  const endpoint = escapeHtml(service.endpoint);
  const health = escapeHtml(service.health_url);
  const api = escapeHtml(service.api_url);
  return `
    <article class="card" data-service="${escapeHtml(service.id)}">
      <div class="card-head">
        <h3>${escapeHtml(service.name)}</h3>
        <span class="state ${state}">${escapeHtml(stateLabel(service.state))}</span>
      </div>
      <p class="description">${escapeHtml(service.description)}</p>
      <div class="endpoint-box">
        <div class="endpoint-row">
          <span class="endpoint-label">Endpoint</span>
          <a href="${endpoint}" target="_blank" rel="noreferrer">${endpoint}</a>
          <button class="copy" data-copy="${endpoint}" aria-label="Copy endpoint" title="Copy endpoint">⧉</button>
        </div>
        <div class="endpoint-row">
          <span class="endpoint-label">Health</span>
          <a href="${health}" target="_blank" rel="noreferrer">${health}</a>
          <span></span>
        </div>
        <div class="endpoint-row">
          <span class="endpoint-label">Chat API</span>
          <a href="${api}" target="_blank" rel="noreferrer">${api}</a>
          <span></span>
        </div>
      </div>
      <div class="card-foot">
        <code class="container-name">${escapeHtml(service.container)}</code>
        <button class="action-button ${running ? "stop" : "start"}" data-action="${running ? "stop" : "start"}" data-id="${escapeHtml(service.id)}">
          ${running ? "Stop service" : "Start service"}
        </button>
      </div>
      ${service.status ? `<p class="message">${escapeHtml(service.status)}</p>` : ""}
    </article>`;
}

async function loadServices() {
  refreshButton.disabled = true;
  try {
    const response = await fetch("/api/containers", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Unable to read Podman status.");
    serviceRoot.innerHTML = payload.services.map(card).join("");
    notice.hidden = true;
    notice.classList.remove("error");
  } catch (error) {
    notice.textContent = error.message;
    notice.hidden = false;
    notice.classList.add("error");
    serviceRoot.innerHTML = '<div class="loading">Container status is unavailable.</div>';
  } finally {
    refreshButton.disabled = false;
  }
}

async function runAction(button) {
  const action = button.dataset.action;
  const serviceId = button.dataset.id;
  button.disabled = true;
  notice.hidden = true;
  try {
    const response = await fetch(`/api/containers/${encodeURIComponent(serviceId)}/${action}`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "The action failed.");
    await loadServices();
    notice.textContent = payload.message;
    notice.hidden = false;
    notice.classList.remove("error");
  } catch (error) {
    notice.textContent = error.message;
    notice.hidden = false;
    notice.classList.add("error");
    button.disabled = false;
  }
}

document.addEventListener("click", (event) => {
  const actionButton = event.target.closest("button[data-action]");
  if (actionButton) runAction(actionButton);
  const copyButton = event.target.closest("button[data-copy]");
  if (copyButton) navigator.clipboard.writeText(copyButton.dataset.copy);
});

refreshButton.addEventListener("click", loadServices);
loadServices();
window.setInterval(loadServices, 10000);
