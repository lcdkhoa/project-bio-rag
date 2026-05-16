"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { useEffect } from "react";
import Image from "next/image";

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

export interface ImageData {
  image_path: string;
  label?: string;
  metadata?: Record<string, any>;
}

interface ImageModalProps {
  isOpen: boolean;
  onClose: () => void;
  image: ImageData | null;
}

export default function ImageModal({ isOpen, onClose, image }: ImageModalProps) {
  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  if (!image) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
          />
          
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="relative w-full max-w-4xl bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-slate-50/80">
              <h3 className="font-medium text-slate-900 truncate pr-4">
                {image.label || "Image Viewer"}
              </h3>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-500 hover:text-slate-900 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Image Container */}
            <div className="flex-1 p-6 flex items-center justify-center bg-slate-100/50">
              <div className="relative w-full h-[50vh] min-h-[300px]">
                <Image
                  src={formatImagePath(image.image_path)}
                  alt={image.label || "RAG output image"}
                  fill
                  className="object-contain rounded-lg shadow-sm border border-slate-200 bg-white"
                />
              </div>
            </div>

            {/* Metadata Footer (if exists) */}
            {image.metadata && Object.keys(image.metadata).length > 0 && (
              <div className="p-5 border-t border-slate-100 bg-slate-50 max-h-48 overflow-y-auto text-xs sm:text-sm">
                <div className="font-semibold text-slate-700 mb-3">Metadata Information</div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Object.entries(image.metadata).map(([key, value]) => (
                    <div key={key} className="flex flex-col bg-white p-2.5 rounded-lg border border-slate-100 shadow-sm">
                      <span className="text-slate-500 font-medium mb-1">{key}:</span>
                      <span className="text-slate-800 break-words">
                        {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
