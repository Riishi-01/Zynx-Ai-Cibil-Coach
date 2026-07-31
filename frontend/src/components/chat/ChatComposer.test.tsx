import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { COPY } from '../../copy';
import { ChatComposer } from './ChatComposer';

describe('ChatComposer', () => {
  it('renders the textarea and a disabled send button by default', () => {
    render(<ChatComposer onSend={vi.fn()} onStop={vi.fn()} streaming={false} />);
    const textarea = screen.getByLabelText(COPY.chat.composerPlaceholder);
    expect(textarea).toBeInTheDocument();
    const send = screen.getByRole('button', { name: COPY.chat.sendAria });
    expect(send).toBeInTheDocument();
    expect(send).toBeDisabled();
  });

  it('enables send once the textarea has content', async () => {
    const user = userEvent.setup();
    render(<ChatComposer onSend={vi.fn()} onStop={vi.fn()} streaming={false} />);
    const send = screen.getByRole('button', { name: COPY.chat.sendAria });

    await user.type(
      screen.getByLabelText(COPY.chat.composerPlaceholder),
      'How long does a late stay?',
    );

    expect(send).toBeEnabled();
  });

  it('sends the trimmed content on send click and clears the input', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} onStop={vi.fn()} streaming={false} />);
    const textarea = screen.getByLabelText(COPY.chat.composerPlaceholder);

    await user.type(textarea, '   what is rate shopping   ');
    await user.click(screen.getByRole('button', { name: COPY.chat.sendAria }));

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith('what is rate shopping');
    expect(textarea).toHaveValue('');
  });

  it('sends on Enter but inserts a newline on Shift+Enter', async () => {
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} onStop={vi.fn()} streaming={false} />);
    const textarea = screen.getByLabelText(
      COPY.chat.composerPlaceholder,
    ) as HTMLTextAreaElement;

    fireEvent.change(textarea, { target: { value: 'hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
    // After Shift+Enter the textarea is still active and onSend not called.
    expect(onSend).not.toHaveBeenCalled();

    // Now add the newline to the value the way the real textarea would.
    fireEvent.change(textarea, { target: { value: 'hello\nworld' } });
    expect(textarea.value).toBe('hello\nworld');

    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
    expect(onSend).toHaveBeenCalled();
    const sent = onSend.mock.calls[0][0] as string;
    expect(sent.startsWith('hello')).toBe(true);
  });

  it('disables input and shows stop button while streaming', async () => {
    const user = userEvent.setup();
    const onStop = vi.fn();
    render(<ChatComposer onSend={vi.fn()} onStop={onStop} streaming={true} />);

    const textarea = screen.getByLabelText(COPY.chat.composerPlaceholder);
    expect(textarea).toBeDisabled();

    await user.click(screen.getByRole('button', { name: COPY.chat.stopAria }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('refuses to submit while streaming even if the input has content', async () => {
    const onSend = vi.fn();
    render(
      <ChatComposer onSend={onSend} onStop={vi.fn()} streaming={true} />,
    );
    const textarea = screen.getByLabelText(
      COPY.chat.composerPlaceholder,
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'should not send' } });
    fireEvent.click(screen.getByRole('button', { name: COPY.chat.stopAria }));
    expect(onSend).not.toHaveBeenCalled();
  });
});
