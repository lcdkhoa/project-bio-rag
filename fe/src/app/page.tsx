"use client";

import { useState, useEffect } from "react";
import Login from "../components/Login";
import ChatInterface from "../components/ChatInterface";
import ImageModal, { ImageData } from "../components/ImageModal";

export default function Home() {
  const [userName, setUserName] = useState<string | null>(null);
  const [isMounted, setIsMounted] = useState(false);
  const [selectedImage, setSelectedImage] = useState<ImageData | null>(null);

  useEffect(() => {
    // Client-side hydration check & load user from local storage
    setIsMounted(true);
    const savedUser = localStorage.getItem("rag_user_name");
    if (savedUser) {
      setUserName(savedUser);
    }
  }, []);

  const handleLogin = (name: string) => {
    localStorage.setItem("rag_user_name", name);
    setUserName(name);
  };

  const handleLogout = () => {
    localStorage.removeItem("rag_user_name");
    setUserName(null);
  };

  if (!isMounted) return null;

  return (
    <main className="flex-1 flex flex-col items-center overflow-hidden">
      {userName ? (
        <ChatInterface 
          userName={userName} 
          onLogout={handleLogout}
          onImageClick={(img) => setSelectedImage(img)} 
        />
      ) : (
        <Login onLogin={handleLogin} />
      )}

      {/* Global Image Modal */}
      <ImageModal 
        isOpen={!!selectedImage} 
        onClose={() => setSelectedImage(null)} 
        image={selectedImage} 
      />
    </main>
  );
}
