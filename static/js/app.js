// ============================================================
// KAIROZEN SMM PANEL — global JS
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  // Mobile nav toggle
  const burger = document.getElementById("navBurger");
  const mobileNav = document.getElementById("navMobile");
  if (burger && mobileNav) {
    burger.addEventListener("click", () => {
      mobileNav.classList.toggle("open");
    });
  }

  // Auto-dismiss flash messages
  document.querySelectorAll(".flash").forEach((el) => {
    setTimeout(() => {
      el.style.transition = "opacity 0.4s, transform 0.4s";
      el.style.opacity = "0";
      el.style.transform = "translateY(-6px)";
      setTimeout(() => el.remove(), 400);
    }, 6000);
  });
});

// ------------------------------------------------------------
// Copy to clipboard helper (used by API key page)
// ------------------------------------------------------------
function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    if (btn) {
      const original = btn.textContent;
      btn.textContent = "បានចម្លង!";
      setTimeout(() => (btn.textContent = original), 1500);
    }
  });
}

// ------------------------------------------------------------
// Order status refresh (dashboard/orders.html)
// ------------------------------------------------------------
async function refreshOrderStatus(orderId, btn) {
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/dashboard/orders/${orderId}/refresh`, { method: "POST" });
    const data = await res.json();
    if (data.ok) {
      const badge = document.getElementById(`status-${orderId}`);
      const remainsCell = document.getElementById(`remains-${orderId}`);
      if (badge) {
        badge.textContent = data.status;
        badge.className = `badge badge-${data.status}`;
      }
      if (remainsCell && data.remains !== undefined) {
        remainsCell.textContent = data.remains;
      }
    } else {
      alert(data.error || "Refresh failed");
    }
  } catch (e) {
    alert("មានបញ្ហា network");
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ------------------------------------------------------------
// Deposit payment polling (dashboard/deposit_show.html)
// ------------------------------------------------------------
function startDepositPolling(depositId) {
  const statusEl = document.getElementById("depositStatus");
  if (!statusEl) return;

  let attempts = 0;
  const maxAttempts = 60; // ~5 min at 5s interval

  const poll = async () => {
    attempts++;
    try {
      const res = await fetch(`/dashboard/deposit/${depositId}/check`, { method: "POST" });
      const data = await res.json();

      if (data.status === "paid") {
        statusEl.textContent = "✓ ទូទាត់ជោគជ័យ! Balance ត្រូវបានបញ្ចូល";
        statusEl.classList.add("is-paid");
        setTimeout(() => (window.location.href = "/dashboard/"), 1800);
        return;
      }

      if (data.manual_required) {
        statusEl.textContent = "កំពុងរង់ចាំ admin confirm ដោយដៃ...";
      } else {
        statusEl.textContent = `កំពុងរង់ចាំការទូទាត់... (${attempts})`;
      }
    } catch (e) {
      statusEl.textContent = "កំពុងពិនិត្យ...";
    }

    if (attempts < maxAttempts) {
      setTimeout(poll, 5000);
    } else {
      statusEl.textContent = "QR ផុតកំណត់សម័យ។ សូម refresh ទំព័រ ដើម្បីបង្កើត QR ថ្មី";
    }
  };

  setTimeout(poll, 5000);
}
