function updateStageHighlight(stage, runStatus) {
  const normalizedStage = (stage || "").split(" (")[0];
  const stageOrder = [
    "Preparing analysis",
    "Crawling",
    "Discovery",
    "Navigation Selection",
    "Lighthouse",
    "Completed",
  ];
  const currentIndex = stageOrder.indexOf(normalizedStage);

  document.querySelectorAll(".stage-item").forEach((item) => {
    const itemStage = item.dataset.stage;
    const statusNode = item.querySelector(".stage-status");
    item.classList.toggle("active", itemStage === normalizedStage);

    statusNode.className = "stage-status";

    if (runStatus === "failed" && itemStage === "Failed") {
      statusNode.textContent = "Error";
      statusNode.classList.add("error");
      return;
    }

    if (itemStage === "Failed") {
      statusNode.textContent = runStatus === "completed" ? "Not Used" : "Waiting";
      statusNode.classList.add(runStatus === "completed" ? "completed" : "waiting");
      return;
    }

    const itemIndex = stageOrder.indexOf(itemStage);
    if (runStatus === "completed" && itemStage === "Completed") {
      statusNode.textContent = "Completed";
      statusNode.classList.add("completed");
    } else if (itemIndex === -1) {
      statusNode.textContent = "Waiting";
      statusNode.classList.add("waiting");
    } else if (itemIndex < currentIndex) {
      statusNode.textContent = "Completed";
      statusNode.classList.add("completed");
    } else if (itemIndex === currentIndex) {
      statusNode.textContent =
        runStatus === "completed" && itemStage !== "Completed" ? "Completed" : "In Progress";
      statusNode.classList.add(
        runStatus === "completed" && itemStage !== "Completed" ? "completed" : "in-progress"
      );
    } else {
      statusNode.textContent = "Waiting";
      statusNode.classList.add("waiting");
    }
  });
}

function updateStatusBadge(status) {
  const badge = document.getElementById("status-badge");
  badge.textContent = status;
  badge.className = `badge ${status}`;
}

function renderEvents(run) {
  const events = document.getElementById("events");
  events.innerHTML = "";
  run.events
    .slice()
    .reverse()
    .forEach((event) => {
      const item = document.createElement("li");
      item.innerHTML = `
        <div class="timeline-time">${event.timestamp}</div>
        <div class="timeline-message">${event.message}</div>
      `;
      events.appendChild(item);
    });
}

function applyStateClass(node, value) {
  node.className = "stage-status";
  if (value === "Completed") {
    node.classList.add("completed");
  } else if (value === "Error") {
    node.classList.add("error");
  } else if (value === "In Progress") {
    node.classList.add("in-progress");
  } else {
    node.classList.add("waiting");
  }
}

function mapRegionStageToState(value, runStatus) {
  if (runStatus === "failed" && value && value !== "Completed") {
    return "Error";
  }
  if (value === "Completed") {
    return "Completed";
  }
  if (value && value !== "Waiting") {
    return "In Progress";
  }
  return "Waiting";
}

function renderRegionStatuses(run) {
  const statuses = run.region_statuses || {};
  const indiaStage = statuses["India - Mumbai"] || "Waiting";
  const usStage = statuses["US West - San Francisco"] || "Waiting";
  const londonStage = statuses["Europe - London"] || "Waiting";

  document.getElementById("region-india").textContent = indiaStage;
  document.getElementById("region-us").textContent = usStage;
  document.getElementById("region-london").textContent = londonStage;

  const indiaState = mapRegionStageToState(indiaStage, run.status);
  const usState = mapRegionStageToState(usStage, run.status);
  const londonState = mapRegionStageToState(londonStage, run.status);

  const indiaStatus = document.getElementById("region-india-status");
  const usStatus = document.getElementById("region-us-status");
  const londonStatus = document.getElementById("region-london-status");

  indiaStatus.textContent = indiaState;
  usStatus.textContent = usState;
  londonStatus.textContent = londonState;

  applyStateClass(indiaStatus, indiaState);
  applyStateClass(usStatus, usState);
  applyStateClass(londonStatus, londonState);
}

function renderError(run) {
  const box = document.getElementById("error-box");
  if (run.error) {
    box.style.display = "block";
    box.textContent = `Run error: ${run.error}`;
  } else {
    box.style.display = "none";
    box.textContent = "";
  }
}

async function refreshRun(runId) {
  const response = await fetch(`/api/runs/${runId}`);
  const run = await response.json();

  updateStatusBadge(run.status);
  document.getElementById("page-count").textContent = run.pages.length;
  document.getElementById("report-link-top").href = run.report_url || "#";

  updateStageHighlight(run.current_stage, run.status);
  renderEvents(run);
  renderRegionStatuses(run);
  renderError(run);
}

function initRunPage(runId, currentStage, currentStatus) {
  updateStageHighlight(currentStage, currentStatus);
  setInterval(() => refreshRun(runId), 2000);
  refreshRun(runId);
}
