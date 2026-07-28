import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { COPY } from '../../copy';
import { CUSTOMERS, type CustomerOption } from '../../data/customers';
import { isPanValid, normalizePan } from '../../lib/validation';

interface DropdownProps {
  /** Currently selected PAN card number, or '' when nothing is chosen. */
  value: string;
  /** Called with the canonical (uppercase, trimmed) PAN when the user picks an option. */
  onChange: (pan: string) => void;
  /** Disable the control while the parent is submitting, etc. */
  disabled?: boolean;
  /** Override the default label, defaults to "PAN". */
  label?: string;
  /** Override the placeholder shown when the input is empty and closed. */
  placeholder?: string;
}

/**
 * Searchable combobox that lets the user pick a PAN card number from a
 * static list of synthetic customers. Rows render as `${pan} - ${first_name}`
 * (e.g. "ABCPS1234A - Anjali") so users can identify the right record by
 * first name; on selection, only the PAN is emitted to the parent via
 * `onChange`.
 *
 * Implements the WAI-ARIA 1.2 combobox pattern manually so the project stays
 * zero-runtime-dep — see frontend_docs/SPEC.md §A11Y. Keyboard support:
 *   - ArrowDown / ArrowUp move the active descendant
 *   - Home / End jump to first / last option
 *   - Enter selects the active option
 *   - Escape closes the list and returns focus to the input
 *   - Tab commits focus changes and closes the list
 */
export function Dropdown({
  value,
  onChange,
  disabled = false,
  label = 'PAN',
  placeholder = COPY.dropdown.placeholder,
}: DropdownProps) {
  const inputId = useId();
  const listboxId = useId();
  const hintId = useId();

  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [flipUp, setFlipUp] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedLabel = useMemo(() => {
    if (!value) return '';
    const match = CUSTOMERS.find((c) => c.pan_card === value);
    return match ? formatOption(match) : value;
  }, [value]);

  const filtered = useMemo<CustomerOption[]>(() => {
    const q = query.trim().toLowerCase();
    if (q === '') return [...CUSTOMERS];
    return CUSTOMERS.filter(
      (c) =>
        c.pan_card.toLowerCase().includes(q) || c.first_name.toLowerCase().includes(q),
    );
  }, [query]);

  // When the filter changes (or the list opens), keep the active descendant
  // within bounds and prefer the first match.
  useEffect(() => {
    setActiveIndex((prev) => {
      if (filtered.length === 0) return 0;
      return Math.min(prev, filtered.length - 1);
    });
  }, [filtered]);

  // Scroll the active descendant into view as the user ArrowDown/ArrowUps
  // through the list — otherwise the highlight can drift off-screen.
  useEffect(() => {
    if (!open) return;
    const list = listRef.current;
    if (!list || typeof list.querySelector !== 'function') return;
    const active = list.querySelector<HTMLElement>('[aria-selected="true"], .dropdown-option--active');
    // jsdom doesn't implement scrollIntoView; guard the call.
    if (active && typeof active.scrollIntoView === 'function') {
      active.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIndex, open]);

  // Decide whether to render the listbox above the input when the bottom
  // edge would clip out of the viewport. Re-evaluated on every open.
  useEffect(() => {
    if (!open) {
      setFlipUp(false);
      return;
    }
    const root = containerRef.current;
    if (!root) return;
    const rect = root.getBoundingClientRect();
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    // 240px is the listbox max-height in dropdown.css.
    const wouldClip = rect.bottom + 240 + 8 > viewportHeight;
    setFlipUp(wouldClip);
  }, [open]);

  const closeList = useCallback(() => {
    setOpen(false);
    setQuery('');
    setActiveIndex(0);
  }, []);

  // Click-outside closes the popover.
  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: MouseEvent) {
      const root = containerRef.current;
      if (root && event.target instanceof Node && !root.contains(event.target)) {
        closeList();
      }
    }
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open, closeList]);

  function selectOption(option: CustomerOption) {
    onChange(normalizePan(option.pan_card));
    closeList();
    inputRef.current?.focus();
  }

  function handleInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const next = event.target.value;
    setQuery(next);
    if (!open) setOpen(true);
    // If the user types a valid full PAN, surface it as the value too so the
    // submit gate lights up without a click — useful for power users who
    // already know the PAN.
    const normalized = normalizePan(next);
    if (isPanValid(normalized)) {
      onChange(normalized);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      if (filtered.length === 0) return;
      setActiveIndex((i) => (i + 1) % filtered.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      if (filtered.length === 0) return;
      setActiveIndex((i) => (i - 1 + filtered.length) % filtered.length);
    } else if (event.key === 'Home') {
      if (!open) return;
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === 'End') {
      if (!open) return;
      event.preventDefault();
      setActiveIndex(filtered.length - 1);
    } else if (event.key === 'Enter') {
      if (!open) return;
      event.preventDefault();
      const choice = filtered[activeIndex];
      if (choice) selectOption(choice);
    } else if (event.key === 'Escape') {
      if (open) {
        event.preventDefault();
        closeList();
      }
    } else if (event.key === 'Tab') {
      // Commit the change in focus without selecting — Tab shouldn't pick.
      closeList();
    }
  }

  function handleFocus() {
    // Open the list on focus so keyboard users can immediately ArrowDown.
    if (!disabled) setOpen(true);
  }

  // Reset the visible query when the parent resets the PAN (e.g. re-opening
  // the form via the chip).
  useEffect(() => {
    if (value === '') setQuery('');
  }, [value]);

  const showListbox = open && !disabled;
  const activeId =
    showListbox && filtered.length > 0
      ? `${listboxId}-opt-${activeIndex}`
      : undefined;

  return (
    <div className="field dropdown" ref={containerRef}>
      <label htmlFor={inputId} className="field-label">
        {label}
      </label>
      <div className="field-input-wrap">
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          role="combobox"
          className="field-input field-input--mono"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          placeholder={placeholder}
          value={open ? query : selectedLabel || query}
          onChange={handleInputChange}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          aria-autocomplete="list"
          aria-expanded={showListbox}
          aria-controls={listboxId}
          aria-activedescendant={activeId}
          aria-describedby={hintId}
          aria-invalid={value !== '' && !isPanValid(value)}
        />
        <span className="dropdown-caret" aria-hidden="true">
          ▾
        </span>
      </div>

      {showListbox && (
        <ul
          ref={listRef}
          id={listboxId}
          role="listbox"
          className={`dropdown-listbox${flipUp ? ' dropdown-listbox--flip' : ''}`}
          aria-label={`${label} options`}
        >
          {filtered.length === 0 ? (
            <li className="dropdown-empty" role="presentation">
              {COPY.dropdown.empty}
            </li>
          ) : (
            filtered.map((option, index) => {
              const optionId = `${listboxId}-opt-${index}`;
              const isActive = index === activeIndex;
              const isSelected = option.pan_card === value;
              return (
                <li
                  key={option.pan_card}
                  id={optionId}
                  role="option"
                  className={`dropdown-option${isActive ? ' dropdown-option--active' : ''}${isSelected ? ' dropdown-option--selected' : ''}`}
                  aria-selected={isSelected}
                  onMouseEnter={() => setActiveIndex(index)}
                  onMouseDown={(event) => {
                    // mousedown (not click) so the input doesn't blur first
                    // and cancel the selection.
                    event.preventDefault();
                    selectOption(option);
                  }}
                >
                  <span className="dropdown-option-pan">{option.pan_card}</span>
                  <span className="dropdown-option-sep" aria-hidden="true">
                    -
                  </span>
                  <span className="dropdown-option-name">{option.first_name}</span>
                </li>
              );
            })
          )}
        </ul>
      )}

      <p id={hintId} className="field-hint">
        {value && isPanValid(value)
          ? COPY.dropdown.hintSelected(selectedLabel)
          : COPY.dropdown.hintDefault}
      </p>
    </div>
  );
}

function formatOption(option: CustomerOption): string {
  return `${option.pan_card} - ${option.first_name}`;
}
