import '@testing-library/jest-dom/vitest';

// jsdom + vitest leave `window.localStorage` without the standard Storage
// methods in some configurations (see SecurityError "opaque origin" in
// tests). The conversationStore is written defensively, but the store
// tests need an in-memory implementation. Mount it only when jsdom
// didn't already provide one.
if (
  typeof window !== 'undefined' &&
  (!window.localStorage ||
    typeof window.localStorage.setItem !== 'function')
) {
  const memory = new Map<string, string>();
  const fakeStorage = {
    getItem: (key: string) => (memory.has(key) ? memory.get(key)! : null),
    setItem: (key: string, value: string) => {
      memory.set(key, String(value));
    },
    removeItem: (key: string) => {
      memory.delete(key);
    },
    clear: () => {
      memory.clear();
    },
    key: (index: number) => Array.from(memory.keys())[index] ?? null,
    get length() {
      return memory.size;
    },
  } as Storage;
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    get: () => fakeStorage,
  });
}
