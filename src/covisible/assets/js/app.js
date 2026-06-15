/**
 * Covisible — Interactive Report JavaScript
 */

(function() {
    'use strict';

    // ===== Theme Toggle =====
    function initTheme() {
        const root = document.documentElement;
        const mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');

        // The inline <head> script applies the initial theme (saved or OS) before
        // paint; fall back here in case it did not run.
        if (!root.getAttribute('data-theme')) {
            const saved = localStorage.getItem('covisible-theme');
            root.setAttribute('data-theme', saved || (mq && mq.matches ? 'dark' : 'light'));
        }

        // Follow the OS preference live, but only until the user picks a theme.
        if (mq && mq.addEventListener) {
            mq.addEventListener('change', (e) => {
                if (!localStorage.getItem('covisible-theme')) {
                    root.setAttribute('data-theme', e.matches ? 'dark' : 'light');
                }
            });
        }

        const toggle = document.getElementById('theme-toggle');
        if (!toggle) return;
        toggle.addEventListener('click', () => {
            const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            root.setAttribute('data-theme', next);
            localStorage.setItem('covisible-theme', next);
        });
    }

    // ===== File Search =====
    function initSearch() {
        const searchInput = document.getElementById('file-search');
        const table = document.getElementById('files-table');
        if (!searchInput || !table) return;

        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const rows = table.querySelectorAll('tbody .file-row');

            rows.forEach(row => {
                const path = row.dataset.path.toLowerCase();
                const matches = path.includes(query);
                row.style.display = matches ? '' : 'none';
            });
        });
    }

    // ===== Table Sorting =====
    function initTableSort() {
        const table = document.getElementById('files-table');
        if (!table) return;

        const headers = table.querySelectorAll('th.sortable');
        let currentSort = { column: null, ascending: true };

        headers.forEach(header => {
            header.addEventListener('click', () => {
                const column = header.dataset.sort;
                const ascending = currentSort.column === column ? !currentSort.ascending : true;
                currentSort = { column, ascending };

                sortTable(table, column, ascending);
                updateSortIndicators(headers, header, ascending);
            });
        });
    }

    function sortTable(table, column, ascending) {
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('.file-row'));

        rows.sort((a, b) => {
            let aVal, bVal;

            switch (column) {
                case 'name':
                    aVal = a.dataset.path;
                    bVal = b.dataset.path;
                    break;
                case 'new':
                    aVal = parseInt(a.cells[1]?.textContent || '0');
                    bVal = parseInt(b.cells[1]?.textContent || '0');
                    break;
                case 'uncovered':
                    aVal = parseInt(a.cells[2]?.textContent || '0');
                    bVal = parseInt(b.cells[2]?.textContent || '0');
                    break;
                case 'new-coverage':
                case 'coverage':
                    const idx = column === 'coverage' ? -1 : 3;
                    const aCell = idx === -1 ? a.cells[a.cells.length - 1] : a.cells[idx];
                    const bCell = idx === -1 ? b.cells[b.cells.length - 1] : b.cells[idx];
                    aVal = parseFloat(aCell?.textContent || '0');
                    bVal = parseFloat(bCell?.textContent || '0');
                    break;
                default:
                    return 0;
            }

            if (typeof aVal === 'string') {
                return ascending ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            }
            return ascending ? aVal - bVal : bVal - aVal;
        });

        rows.forEach(row => tbody.appendChild(row));
    }

    function updateSortIndicators(headers, activeHeader, ascending) {
        headers.forEach(h => {
            h.textContent = h.textContent.replace(/ [↑↓]$/, '');
        });
        activeHeader.textContent += ascending ? ' ↑' : ' ↓';
    }

    // ===== Source View Controls =====
    function initSourceControls() {
        const showAllToggle = document.getElementById('show-all-lines');
        const showLineNumbers = document.getElementById('show-line-numbers');
        const sourceTable = document.getElementById('source-table');

        if (!sourceTable) return;

        if (showAllToggle) {
            // Set initial state
            if (showAllToggle.checked) {
                sourceTable.classList.add('show-all');
            }

            showAllToggle.addEventListener('change', (e) => {
                sourceTable.classList.toggle('show-all', e.target.checked);
            });
        }

        if (showLineNumbers) {
            showLineNumbers.addEventListener('change', (e) => {
                const lineNumbers = sourceTable.querySelectorAll('.line-number');
                lineNumbers.forEach(ln => {
                    ln.style.visibility = e.target.checked ? 'visible' : 'hidden';
                });
            });
        }
    }

    // ===== Go to Line =====
    function initGoToLine() {
        document.querySelectorAll('[data-goto-line]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const lineNum = link.dataset.gotoLine;
                const lineRow = document.querySelector(`.source-line[data-line="${lineNum}"]`);
                if (lineRow) {
                    // Show all lines first
                    const showAllToggle = document.getElementById('show-all-lines');
                    if (showAllToggle && !showAllToggle.checked) {
                        showAllToggle.checked = true;
                        showAllToggle.dispatchEvent(new Event('change'));
                    }

                    lineRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    lineRow.classList.add('highlight');
                    setTimeout(() => lineRow.classList.remove('highlight'), 2000);
                }
            });
        });
    }

    // ===== Keyboard Navigation =====
    function initKeyboardNav() {
        document.addEventListener('keydown', (e) => {
            // Focus search on /
            if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
                const searchInput = document.getElementById('file-search');
                if (searchInput && document.activeElement !== searchInput) {
                    e.preventDefault();
                    searchInput.focus();
                }
            }

            // Toggle theme on t
            if (e.key === 't' && !e.ctrlKey && !e.metaKey && document.activeElement.tagName !== 'INPUT') {
                const toggle = document.getElementById('theme-toggle');
                if (toggle) toggle.click();
            }

            // Escape to blur
            if (e.key === 'Escape') {
                document.activeElement.blur();
            }
        });
    }

    // ===== Initialize =====
    function init() {
        initTheme();
        initSearch();
        initTableSort();
        initSourceControls();
        initGoToLine();
        initKeyboardNav();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
