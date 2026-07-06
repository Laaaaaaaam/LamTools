import { describe, expect, it } from 'vitest';
import { findActiveSlashCandidate, parseComposerSyntax } from '../src/composer/syntax';

describe('parseComposerSyntax', () => {
  it('parses slash commands only at input start or after whitespace', () => {
    expect(parseComposerSyntax('/compact')).toMatchObject([
      { kind: 'slash', start: 0, end: 8, value: 'compact' },
    ]);
    expect(parseComposerSyntax('请用 /brainstorming 梳理一下')).toMatchObject([
      { kind: 'slash', value: 'brainstorming' },
    ]);
    expect(parseComposerSyntax('abc/compact')).toEqual([]);
    expect(parseComposerSyntax('https://example.com/a/b')).toEqual([]);
    expect(parseComposerSyntax('C:/tmp/a.txt')).toEqual([]);
  });

  it('ignores slash commands inside quotes and markdown code', () => {
    expect(parseComposerSyntax('"/compact"')).toEqual([]);
    expect(parseComposerSyntax('\'/compact\'')).toEqual([]);
    expect(parseComposerSyntax('`/compact`')).toEqual([]);
    expect(parseComposerSyntax('```md\n/compact\n```')).toEqual([]);
  });

  it('keeps at-resource parsing aligned with slash parsing', () => {
    expect(parseComposerSyntax('@E:\\tmp\\a.txt')).toMatchObject([
      { kind: 'resource', value: 'E:\\tmp\\a.txt' },
    ]);
    expect(parseComposerSyntax('abc@E:\\tmp\\a.txt')).toEqual([]);
    expect(parseComposerSyntax('email@example.com')).toEqual([]);
    expect(parseComposerSyntax('`@E:\\tmp\\a.txt`')).toEqual([]);
  });

  it('finds the active slash candidate at the cursor', () => {
    const text = '请用 /comp';
    expect(findActiveSlashCandidate(text, text.length)).toMatchObject({
      kind: 'slash',
      value: 'comp',
    });
    expect(findActiveSlashCandidate('abc/comp', 8)).toBeNull();
  });
});
