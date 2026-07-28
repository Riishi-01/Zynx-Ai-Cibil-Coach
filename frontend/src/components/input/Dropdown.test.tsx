import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Dropdown } from './Dropdown';

describe('Dropdown', () => {
  it('renders a combobox input labelled PAN', () => {
    render(<Dropdown value="" onChange={() => {}} />);
    const combo = screen.getByRole('combobox', { name: /pan/i });
    expect(combo).toBeInTheDocument();
    expect(combo).toHaveAttribute('aria-expanded', 'false');
  });

  it('opens the listbox on focus and lists all customers', async () => {
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={() => {}} />);

    await user.click(screen.getByRole('combobox', { name: /pan/i }));

    expect(screen.getByRole('listbox')).toBeInTheDocument();
    // The 23-option list should produce 23 options.
    expect(screen.getAllByRole('option')).toHaveLength(23);
  });

  it('formats options as "<PAN> - <first name>"', async () => {
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={() => {}} />);

    await user.click(screen.getByRole('combobox', { name: /pan/i }));

    // The separator span is aria-hidden, so the accessible name concatenates
    // the PAN and first name with whitespace.
    expect(screen.getByRole('option', { name: /ABCPS1234A\s+Anjali/ })).toBeInTheDocument();
  });

  it('selecting an option emits the canonical PAN and closes the listbox', async () => {
    const handleChange = vi.fn();
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={handleChange} />);

    await user.click(screen.getByRole('combobox', { name: /pan/i }));
    await user.click(screen.getByRole('option', { name: /ABCPS1234A\s+Anjali/ }));

    expect(handleChange).toHaveBeenCalledWith('ABCPS1234A');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('filters options by PAN substring', async () => {
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={() => {}} />);

    const combo = screen.getByRole('combobox', { name: /pan/i });
    await user.click(combo);
    await user.keyboard('ABCP');

    const options = screen.getAllByRole('option');
    expect(options.length).toBeGreaterThan(0);
    options.forEach((opt) => {
      expect(opt.textContent?.toLowerCase()).toContain('abcp');
    });
  });

  it('filters options by first-name substring', async () => {
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={() => {}} />);

    const combo = screen.getByRole('combobox', { name: /pan/i });
    await user.click(combo);
    await user.keyboard('Anj');

    const options = screen.getAllByRole('option');
    expect(options.length).toBeGreaterThan(0);
    options.forEach((opt) => {
      expect(opt.textContent?.toLowerCase()).toContain('anj');
    });
  });

  it('shows "No matches" when the query has zero hits', async () => {
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={() => {}} />);

    const combo = screen.getByRole('combobox', { name: /pan/i });
    await user.click(combo);
    await user.keyboard('zzzzz');

    expect(screen.getByText(/no matches/i)).toBeInTheDocument();
  });

  it('keyboard ArrowDown + Enter selects an option without a click', async () => {
    const handleChange = vi.fn();
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={handleChange} />);

    const combo = screen.getByRole('combobox', { name: /pan/i });
    combo.focus();
    // Focus auto-opens the listbox with activeIndex=0. ArrowDown then
    // advances to index 1 (BCDRM2345B - Carlos).
    await user.keyboard('{ArrowDown}{Enter}');

    expect(handleChange).toHaveBeenCalledWith('BCDRM2345B');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('Escape closes the listbox without selecting', async () => {
    const handleChange = vi.fn();
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={handleChange} />);

    await user.click(screen.getByRole('combobox', { name: /pan/i }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(handleChange).not.toHaveBeenCalled();
  });

  it('clicking outside closes the listbox', async () => {
    const user = userEvent.setup();
    render(
      <div>
        <Dropdown value="" onChange={() => {}} />
        <button data-testid="outside">Outside</button>
      </div>,
    );

    await user.click(screen.getByRole('combobox', { name: /pan/i }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    await user.click(screen.getByTestId('outside'));

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('shows the selected label when closed and a value is provided', () => {
    render(<Dropdown value="ABCPS1234A" onChange={() => {}} />);

    const combo = screen.getByRole('combobox', { name: /pan/i }) as HTMLInputElement;
    expect(combo.value).toBe('ABCPS1234A - Anjali');
  });

  it('disabled prop prevents focus, typing, and selecting', async () => {
    const handleChange = vi.fn();
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={handleChange} disabled />);

    const combo = screen.getByRole('combobox', { name: /pan/i }) as HTMLInputElement;
    expect(combo).toBeDisabled();

    // The listbox must not render when disabled.
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    // A click should not toggle the open state.
    await user.click(combo);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('typing a full PAN auto-populates the value without a click', async () => {
    const handleChange = vi.fn();
    const user = userEvent.setup();
    render(<Dropdown value="" onChange={handleChange} />);

    await user.click(screen.getByRole('combobox', { name: /pan/i }));
    await user.keyboard('ABCPS1234A');

    expect(handleChange).toHaveBeenCalledWith('ABCPS1234A');
  });
});
