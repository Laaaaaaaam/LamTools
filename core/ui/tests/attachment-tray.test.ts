import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import AttachmentTray from '../src/components/AttachmentTray.vue';
import ChatThread from '../src/components/ChatThread.vue';
import type { CoreAttachment, CoreMessage } from '../src/types';

const uploaded: CoreAttachment = {
  id: 'att-1',
  filename: 'note.md',
  label: 'note.md',
  mime_type: 'text/markdown',
  size: 120,
  preview_type: 'text',
  status: 'uploaded',
};

describe('AttachmentTray', () => {
  it('renders uploaded and failed attachments with stable actions', async () => {
    const wrapper = mount(AttachmentTray, {
      props: {
        attachments: [
          uploaded,
          {
            ...uploaded,
            id: 'att-2',
            filename: 'bad.png',
            label: 'bad.png',
            mime_type: 'image/png',
            preview_type: 'image',
            status: 'failed',
            error: '上传失败',
          },
        ],
      },
    });

    expect(wrapper.text()).toContain('note.md');
    expect(wrapper.text()).toContain('bad.png');
    expect(wrapper.text()).toContain('上传失败');
    expect(wrapper.text()).toContain('本机打开');

    await wrapper.get('[data-attachment-remove="att-1"]').trigger('click');
    await wrapper.get('[data-attachment-retry="att-2"]').trigger('click');

    expect(wrapper.emitted('remove')?.[0]).toEqual(['att-1']);
    expect(wrapper.emitted('retry')?.[0]).toEqual(['att-2']);
  });

  it('renders user-message attachment parts in ChatThread', () => {
    const messages: CoreMessage[] = [{
      id: 'm-1',
      role: 'user',
      content: '看附件',
      timestamp: '',
      parts: [{
        id: 'm-1:att-1',
        partType: 'attachment',
        status: 'completed',
        content: '',
        label: 'note.md',
        metadata: { attachment: uploaded },
      }],
    }];

    const wrapper = mount(ChatThread, { props: { messages } });

    expect(wrapper.text()).toContain('看附件');
    expect(wrapper.text()).toContain('note.md');
  });
});
