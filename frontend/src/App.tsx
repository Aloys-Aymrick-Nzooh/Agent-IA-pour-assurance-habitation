import { useEffect } from 'react';
import { useActive, useUi } from './state/store';
import { restoreBackendData } from './state/controller';
import { Sidebar } from './components/Sidebar';
import { ChatHeader, NoticeBar } from './components/ChatHeader';
import { MessageList } from './components/MessageList';
import { Composer } from './components/Composer';
import { SourceDrawer } from './components/SourceDrawer';
import { UploadDialog } from './components/UploadDialog';
import { SettingsDialog } from './components/SettingsDialog';

export default function App() {
  const conv = useActive();
  const { sidebarOpen, source, set } = useUi();

  useEffect(() => {
    void restoreBackendData();
  }, []);

  return (
    <div className="app" data-drawer={source !== null}>
      <Sidebar />
      {sidebarOpen && <div className="scrim" onClick={() => set({ sidebarOpen: false })} />}

      <main className="main">
        <ChatHeader conv={conv} />
        <NoticeBar conv={conv} />
        <MessageList conv={conv} />
        <Composer conv={conv} />
      </main>

      <SourceDrawer conv={conv} />
      <UploadDialog />
      <SettingsDialog />
    </div>
  );
}
