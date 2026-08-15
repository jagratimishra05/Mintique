// Mintique — dashboard charts (Chart.js). Reads JSON blobs rendered by
// {{ ... |json_script:"id" }} in dashboard.html and draws 4 charts styled to
// match the app's dark theme.
document.addEventListener("DOMContentLoaded", () => {
  if (typeof Chart === "undefined") return;

  const readJSON = (id) => {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : [];
  };

  const purple = "#a855f7";
  const magenta = "#ec4899";
  const cyan = "#22d3ee";
  const green = "#34d399";
  const textDim = "#9c9cb5";
  const gridColor = "rgba(255,255,255,0.06)";

  Chart.defaults.color = textDim;
  Chart.defaults.font.family = "'Inter', system-ui, sans-serif";

  const sharedGrid = { color: gridColor, drawBorder: false };
  const sharedScales = {
    x: { grid: { display: false }, ticks: { color: textDim } },
    y: { grid: sharedGrid, ticks: { color: textDim }, beginAtZero: true },
  };

  function gradientFill(ctx, color) {
    const g = ctx.createLinearGradient(0, 0, 0, 220);
    g.addColorStop(0, color + "55");
    g.addColorStop(1, color + "00");
    return g;
  }

  // --- NFT Sales (line) ----------------------------------------------------
  const salesCtx = document.getElementById("salesChart");
  if (salesCtx) {
    new Chart(salesCtx, {
      type: "line",
      data: {
        labels: readJSON("salesLabels"),
        datasets: [{
          label: "NFTs sold",
          data: readJSON("salesData"),
          borderColor: purple,
          backgroundColor: gradientFill(salesCtx.getContext("2d"), purple),
          fill: true,
          tension: 0.35,
          pointBackgroundColor: purple,
          pointRadius: 4,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: sharedScales,
      },
    });
  }

  // --- Revenue (bar) ---------------------------------------------------------
  const revenueCtx = document.getElementById("revenueChart");
  if (revenueCtx) {
    new Chart(revenueCtx, {
      type: "bar",
      data: {
        labels: readJSON("salesLabels"),
        datasets: [{
          label: "Revenue (ETH)",
          data: readJSON("revenueData"),
          backgroundColor: magenta,
          borderRadius: 6,
          maxBarThickness: 34,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: sharedScales,
      },
    });
  }

  // --- Views (bar, per NFT) ---------------------------------------------------
  const viewsCtx = document.getElementById("viewsChart");
  if (viewsCtx) {
    new Chart(viewsCtx, {
      type: "bar",
      data: {
        labels: readJSON("nftLabels"),
        datasets: [{
          label: "Views",
          data: readJSON("viewsData"),
          backgroundColor: cyan,
          borderRadius: 6,
          maxBarThickness: 34,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: sharedGrid, ticks: { color: textDim }, beginAtZero: true },
          y: { grid: { display: false }, ticks: { color: textDim } },
        },
      },
    });
  }

  // --- Likes (doughnut, per NFT) ----------------------------------------------
  const likesCtx = document.getElementById("likesChart");
  if (likesCtx) {
    const palette = [purple, magenta, cyan, green, "#fb5b5b"];
    new Chart(likesCtx, {
      type: "doughnut",
      data: {
        labels: readJSON("nftLabels"),
        datasets: [{
          data: readJSON("likesData"),
          backgroundColor: palette,
          borderColor: "#11111f",
          borderWidth: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { color: textDim, boxWidth: 12, padding: 12 } } },
      },
    });
  }
});
