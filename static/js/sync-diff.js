// Sync diff confirmation dialog — supports single diff or multi-file diffs array
(function() {
  "use strict";

  /**
   * Show a side-by-side diff dialog for sync confirmation.
   * @param {Object} options
   * @param {string} options.title - Dialog title
   * @param {Object} [options.diff] - Single diff {file, action, current, new}
   * @param {Array}  [options.diffs] - Array of diff objects (multi-file)
   * @param {Function} options.onConfirm - Called when user confirms
   * @param {Function} [options.onCancel] - Called when user cancels
   */
  window.showSyncDiffDialog = function(options) {
    var existing = document.getElementById("sync-diff-overlay");
    if (existing) existing.remove();

    // Normalize: single diff → array
    var diffs = options.diffs || (options.diff ? [options.diff] : []);
    if (!diffs.length) { if (options.onConfirm) options.onConfirm(); return; }

    var overlay = document.createElement("div");
    overlay.id = "sync-diff-overlay";
    overlay.className = "sync-diff-overlay";

    var dialog = document.createElement("div");
    dialog.className = "sync-diff-dialog";

    // Header
    var header = document.createElement("div");
    header.className = "sync-diff-header";
    var titleText = esc(options.title || "Confirm Sync");
    if (diffs.length > 1) titleText += " (" + diffs.length + " files)";
    header.innerHTML = '<div class="sync-diff-title">' + titleText + "</div>";
    dialog.appendChild(header);

    // Scrollable container for all file diffs
    var container = document.createElement("div");
    container.className = "sync-diff-container";

    diffs.forEach(function(diff) {
      // File header
      var fileHeader = document.createElement("div");
      fileHeader.className = "sync-diff-file-header";
      fileHeader.innerHTML = '<span class="sync-diff-file-name">' + esc(diff.file) + "</span>" +
        ' <span class="sync-diff-file-action">' +
        (diff.action === "replace" ? "Replace" : diff.action === "create" ? "Create" : "Append") + "</span>";
      container.appendChild(fileHeader);

      // Side-by-side panels
      var body = document.createElement("div");
      body.className = "sync-diff-body";

      var leftPanel = document.createElement("div");
      leftPanel.className = "sync-diff-panel sync-diff-left";
      leftPanel.innerHTML = '<div class="sync-diff-panel-header">Current</div>';
      var leftCode = document.createElement("div");
      leftCode.className = "sync-diff-code";
      (diff.current || []).forEach(function(line) {
        var row = document.createElement("div");
        row.className = "sync-diff-line sync-diff-" + line.type;
        row.innerHTML = '<span class="sync-diff-ln">' + line.ln + '</span><span class="sync-diff-text">' + esc(line.text) + "</span>";
        leftCode.appendChild(row);
      });
      leftPanel.appendChild(leftCode);

      var rightPanel = document.createElement("div");
      rightPanel.className = "sync-diff-panel sync-diff-right";
      rightPanel.innerHTML = '<div class="sync-diff-panel-header">New</div>';
      var rightCode = document.createElement("div");
      rightCode.className = "sync-diff-code";
      (diff["new"] || []).forEach(function(line) {
        var row = document.createElement("div");
        row.className = "sync-diff-line sync-diff-" + line.type;
        row.innerHTML = '<span class="sync-diff-ln">' + line.ln + '</span><span class="sync-diff-text">' + esc(line.text) + "</span>";
        rightCode.appendChild(row);
      });
      rightPanel.appendChild(rightCode);

      body.appendChild(leftPanel);
      body.appendChild(rightPanel);

      // Sync scroll per file pair
      leftCode.onscroll = function() { rightCode.scrollTop = leftCode.scrollTop; };
      rightCode.onscroll = function() { leftCode.scrollTop = rightCode.scrollTop; };

      container.appendChild(body);
    });

    dialog.appendChild(container);

    // Footer
    var footer = document.createElement("div");
    footer.className = "sync-diff-footer";
    var cancelBtn = document.createElement("button");
    cancelBtn.className = "btn btn-secondary";
    cancelBtn.textContent = "Cancel";
    cancelBtn.onclick = function() { overlay.remove(); if (options.onCancel) options.onCancel(); };
    var confirmBtn = document.createElement("button");
    confirmBtn.className = "btn btn-primary";
    confirmBtn.textContent = "Confirm Write";
    confirmBtn.onclick = function() { overlay.remove(); if (options.onConfirm) options.onConfirm(); };
    footer.appendChild(cancelBtn);
    footer.appendChild(confirmBtn);
    dialog.appendChild(footer);

    overlay.appendChild(dialog);
    overlay.onclick = function(e) { if (e.target === overlay) { overlay.remove(); if (options.onCancel) options.onCancel(); } };
    document.body.appendChild(overlay);

    function onEsc(e) {
      if (e.key === "Escape") {
        overlay.remove();
        document.removeEventListener("keydown", onEsc);
        if (options.onCancel) options.onCancel();
      }
    }
    document.addEventListener("keydown", onEsc);
  };

  function esc(s) {
    if (window.esc) return window.esc(s);
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
})();
