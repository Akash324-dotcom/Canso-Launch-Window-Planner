export default {
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.js'],
    restoreMocks: true,
    setupFiles: ['tests/setup-clock.js'],
  },
};
