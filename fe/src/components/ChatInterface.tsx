"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { Send, User, Bot, Loader2, ImageIcon, LogOut } from "lucide-react";
import Image from "next/image";
import { sendChatMessage } from "../lib/api";
import type { ImageData } from "./ImageModal";

const formatImagePath = (originalPath: string) => {
  if (!originalPath) return "";
  // Split by either /database/images/ or \database\images\ (case insensitive and handles both separators)
  const parts = originalPath.split(/[\\/]database[\\/]images[\\/]/i);
  if (parts.length > 1) {
    // Ensure the resulting path uses forward slashes for the web URL
    return `/images/${parts[1].replace(/\\/g, '/')}`;
  }
  return originalPath;
};

interface Message {
  id: string;
  role: "user" | "bot";
  content: string;
  images?: ImageData[];
}

interface ChatInterfaceProps {
  userName: string;
  onImageClick: (image: ImageData) => void;
  onLogout: () => void;
}

export default function ChatInterface({ userName, onImageClick, onLogout }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "bot",
      content: `Hello **${userName}**! I am your Biology RAG Assistant. Ask me anything about biology!`,
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await sendChatMessage(userMessage.content);
      
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "bot",
        content: response.answer,
        images: response.images,
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      console.error(error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "bot",
        content: "Sorry, I encountered an error while processing your request.",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen max-h-screen relative max-w-5xl mx-auto w-full bg-white/60 backdrop-blur-md sm:border-x sm:border-slate-200 shadow-xl">
      {/* Header */}
      <header className="h-16 border-b border-slate-200 bg-white/80 backdrop-blur-md flex items-center justify-between px-6 sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center">
            <Bot className="w-6 h-6 text-emerald-600" />
          </div>
          <div>
            <h2 className="text-slate-900 font-semibold">Biology Assistant</h2>
            <p className="text-xs text-emerald-600 flex items-center gap-1 font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              Online
            </p>
          </div>
        </div>
        <button 
          onClick={onLogout}
          className="text-slate-500 hover:text-slate-900 p-2 rounded-lg hover:bg-slate-100 transition-colors flex items-center gap-2 text-sm font-medium"
        >
          <LogOut className="w-4 h-4" />
          <span className="hidden sm:inline">Logout</span>
        </button>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
        {messages.map((msg) => (
          <motion.div
            key={msg.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex gap-4 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
          >
            <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-1 shadow-sm ${
              msg.role === "user" ? "bg-blue-500" : "bg-emerald-500"
            }`}>
              {msg.role === "user" ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-white" />}
            </div>
            
            <div className={`flex flex-col max-w-[85%] sm:max-w-[75%] ${msg.role === "user" ? "items-end" : "items-start"}`}>
              <div className={`px-5 py-3.5 rounded-2xl ${
                msg.role === "user" 
                  ? "bg-blue-600 text-white rounded-tr-sm shadow-md" 
                  : "bg-white text-slate-800 rounded-tl-sm shadow-sm border border-slate-200"
              }`}>
                <div className="whitespace-pre-wrap leading-relaxed text-sm sm:text-base">
                  {/* Basic markdown rendering for bold text and line breaks */}
                  {msg.content.split('**').map((part, i) => i % 2 === 1 ? <strong key={i} className={msg.role === "user" ? "text-white" : "text-emerald-700"}>{part}</strong> : part)}
                </div>
              </div>

              {/* Images Grid */}
              {msg.images && msg.images.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {msg.images.map((img, i) => (
                    <button
                      key={i}
                      onClick={() => onImageClick(img)}
                      className="relative group w-32 h-32 rounded-xl overflow-hidden border border-slate-200 hover:border-emerald-500 transition-colors bg-slate-50 flex-shrink-0 shadow-sm"
                    >
                      <Image 
                        src={formatImagePath(img.image_path)} 
                        alt="attachment" 
                        fill
                        className="object-cover opacity-90 group-hover:opacity-100 transition-opacity"
                      />
                      <div className="absolute inset-0 bg-slate-900/20 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <ImageIcon className="w-6 h-6 text-white drop-shadow-md" />
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        ))}

        {isLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex gap-4 flex-row"
          >
            <div className="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center shrink-0 mt-1 shadow-sm">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div className="px-5 py-3.5 rounded-2xl bg-white rounded-tl-sm border border-slate-200 shadow-sm flex items-center gap-3">
              <Loader2 className="w-5 h-5 text-emerald-500 animate-spin" />
              <span className="text-slate-500 text-sm font-medium">Thinking...</span>
            </div>
          </motion.div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white/80 backdrop-blur-md border-t border-slate-200 relative z-10">
        <form 
          onSubmit={handleSubmit}
          className="max-w-4xl mx-auto relative flex items-end gap-2 bg-slate-50 rounded-2xl p-2 border border-slate-200 focus-within:border-emerald-500/50 focus-within:ring-2 focus-within:ring-emerald-500/20 transition-all shadow-sm"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            placeholder="Ask about biology... (Press Enter to send)"
            className="w-full max-h-32 min-h-[44px] bg-transparent border-none text-slate-900 placeholder-slate-400 focus:ring-0 resize-none py-2.5 px-4 scrollbar-thin scrollbar-thumb-slate-300 outline-none"
            rows={1}
            style={{
              height: 'auto',
            }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="p-3 bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-200 disabled:text-slate-400 text-white rounded-xl transition-colors shrink-0 mb-0.5 mr-0.5 flex items-center justify-center shadow-sm"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
        <div className="text-center mt-2">
          <p className="text-[10px] text-slate-400">AI can make mistakes. Verify important biological information.</p>
        </div>
      </div>
    </div>
  );
}
