// Mintique — swap widget behavior (any supported token → any other token)
document.addEventListener("DOMContentLoaded", () => {
  const amountInput = document.getElementById("swapAmount");
  const estimateEl = document.getElementById("swapEstimate");
  const fromField = document.getElementById("swapFromToken");
  const toField = document.getElementById("swapToToken");
  const fromSelect = document.getElementById("swapFromSelect");
  const toSelect = document.getElementById("swapToSelect");
  const fromBalanceEl = document.getElementById("swapFromBalance");
  const toBalanceEl = document.getElementById("swapToBalance");
  const rateLabel = document.getElementById("swapRateLabel");
  const arrow = document.getElementById("swapArrowBtn");
  if (!amountInput) return;

  let rates = {};
  let balances = {};
  try { rates = JSON.parse(document.body.dataset.cryptoRates || "{}"); } catch (e) {}
  try { balances = JSON.parse(document.body.dataset.cryptoBalances || "{}"); } catch (e) {}
  const feePct = parseFloat(document.body.dataset.feePct || "0.3") / 100;

  function fmt(n, maxDp) {
    return n.toLocaleString(undefined, { maximumFractionDigits: maxDp });
  }

  function recalc() {
    const from = fromSelect.value;
    const to = toSelect.value;
    fromField.value = from;
    toField.value = to;

    fromBalanceEl.textContent = fmt(balances[from] ?? 0, 6);
    toBalanceEl.textContent = fmt(balances[to] ?? 0, 6);

    const rateFrom = rates[from];
    const rateTo = rates[to];
    if (!rateFrom || !rateTo) {
      estimateEl.textContent = "0";
      rateLabel.textContent = "—";
      return;
    }

    const perOne = rateTo / rateFrom;
    rateLabel.textContent = `1 ${from} ≈ ${fmt(perOne, 6)} ${to}`;

    const amt = parseFloat(amountInput.value) || 0;
    const amountInEth = amt / rateFrom;
    const estimate = amountInEth * rateTo * (1 - feePct);
    estimateEl.textContent = `${fmt(estimate, 6)} ${to}`;
  }

  amountInput.addEventListener("input", recalc);
  fromSelect.addEventListener("change", recalc);
  toSelect.addEventListener("change", recalc);

  arrow?.addEventListener("click", () => {
    const currentFrom = fromSelect.value;
    fromSelect.value = toSelect.value;
    toSelect.value = currentFrom;
    recalc();
  });

  recalc();
});
