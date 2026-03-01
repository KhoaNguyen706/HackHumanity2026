import { useState, useRef } from 'react';
import { GoogleGenerativeAI } from "@google/generative-ai";
import type { Highlight, AnalysisResult, EvidenceField } from '../types';
import { AlertCircle } from 'lucide-react';
import RiskBadge from './RiskBadge';



interface SidePanelProps {
    analysis: AnalysisResult;
    selectedHighlight: Highlight | null;
    onSelectTab: (tab: 'overview' | 'details') => void;
    activeTab: 'overview' | 'details';
}

function DataRow<T>({ label, field, suffix = "" }: { label: string, field: EvidenceField<T>, suffix?: string }) {
    const [showQuote, setShowQuote] = useState(false);

    return (
        <div className="group border-b border-[#5A4231]/10 py-4 last:border-0 hover:bg-[#F2E3D5]/20 transition-colors px-4 -mx-4 rounded-xl">
            <div className="flex justify-between items-baseline mb-1">
                <span className="text-[10px] font-black uppercase tracking-widest text-[#8A6B53]">{label}</span>
                <div className="text-right">
                    {field.value !== null ? (
                        <span className="font-black text-[#4A3424] text-lg">
                            {typeof field.value === 'number' && label.toLowerCase().includes('rent') ? `$${field.value.toLocaleString()}` :
                                typeof field.value === 'number' && label.toLowerCase().includes('deposit') ? `$${field.value.toLocaleString()}` :
                                    String(field.value)}{suffix}
                        </span>
                    ) : (
                        <span className="text-rose-500 font-bold text-xs italic tracking-tighter uppercase whitespace-nowrap">Missing: {field.missing_reason}</span>
                    )}
                </div>
            </div>

            {field.evidence_quote && (
                <div className="mt-2">
                    <button
                        onClick={() => setShowQuote(!showQuote)}
                        className="text-[9px] font-black uppercase tracking-tighter text-[#D9734E] hover:underline transition-all underline-offset-2"
                    >
                        {showQuote ? "Hide Evidence" : "View Source Quote"}
                    </button>
                    {showQuote && (
                        <div className="mt-2 p-3 bg-white/60 border border-[#5A4231]/10 rounded-xl text-[13px] font-medium italic text-[#8A6B53] leading-relaxed animate-in fade-in slide-in-from-top-1">
                            "{field.evidence_quote}"
                            {field.ambiguous && (
                                <div className="mt-2 inline-block bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-tighter">
                                    Ambiguous Entry
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default function SidePanel({ analysis, selectedHighlight, onSelectTab, activeTab }: SidePanelProps) {
    const [isTranslating, setIsTranslating] = useState(false);
    const [translatedText, setTranslatedText] = useState<string | null>(null);
    const [currentLanguage, setCurrentLanguage] = useState('English');
    const [showLangMenu, setShowLangMenu] = useState(false);

    const languages = [
        { name: 'Spanish', code: 'es' },
        { name: 'French', code: 'fr' },
        { name: 'Mandarin', code: 'zh' },
        { name: 'Vietnamese', code: 'vi' },
        { name: 'Tagalog', code: 'tl' },
        { name: 'Arabic', code: 'ar' }
    ];

    const [isSpeaking, setIsSpeaking] = useState(false);
    const [showAudioPlayer, setShowAudioPlayer] = useState(false);
    const [autoplayBlocked, setAutoplayBlocked] = useState(false);
    const [audioBlobUrl, setAudioBlobUrl] = useState<string | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const [speakingLanguage, setSpeakingLanguage] = useState<string>('English');

    const handleTestAudio = () => {
        console.log("🎹 Testing System Audio...");
        try {
            const context = new (window.AudioContext || (window as any).webkitAudioContext)();
            const oscillator = context.createOscillator();
            const gainNode = context.createGain();

            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(440, context.currentTime);

            gainNode.gain.setValueAtTime(0.3, context.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 1);

            oscillator.connect(gainNode);
            gainNode.connect(context.destination);

            oscillator.start();
            oscillator.stop(context.currentTime + 1);
            console.log("🔊 Test sound (440Hz Sine) should be playing now.");
        } catch (err) {
            console.error("❌ Audio Hardware Error:", err);
            alert("Your browser/laptop audio system seems to be blocked or unavailable.");
        }
    };

    const stopCurrentAudio = () => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.currentTime = 0;
        }
    };

    // Each language gets a DIFFERENT verified ElevenLabs premade voice + language_code
    const getVoiceConfig = (lang: string): { voiceId: string; voiceName: string } => {
        switch (lang) {
            case 'Vietnamese':
                return { voiceId: 'EXAVITQu4vr4xnSDxMaL', voiceName: 'Bella' };
            case 'Mandarin':
                return { voiceId: 'MF3mGyEYCl7XYWbV9V6O', voiceName: 'Elli' };
            case 'Spanish':
                return { voiceId: 'ErXwobaYiN019PkySvjV', voiceName: 'Antoni' };
            case 'French':
                return { voiceId: 'ThT5KcBeYPX3keUQqHPh', voiceName: 'Dorothy' };
            case 'Arabic':
                return { voiceId: 'VR6AewLTigWG4xSOukaG', voiceName: 'Arnold' };
            case 'Tagalog':
                return { voiceId: 'AZnzlk1XvdvUeBnXmlld', voiceName: 'Domi' };
            default:
                return { voiceId: '21m00Tcm4TlvDq8ikWAM', voiceName: 'Rachel' };
        }
    };

    const handleSpeak = async (text: string, lang: string = 'English') => {
        console.log("🎤 handleSpeak triggered for text:", text.substring(0, 50) + "...");
        console.log("🌍 Language:", lang);

        // Stop any currently playing audio first
        stopCurrentAudio();
        setSpeakingLanguage(lang);
        setIsSpeaking(true);
        setShowAudioPlayer(true);

        try {
            const { voiceId, voiceName } = getVoiceConfig(lang);
            const API_KEY = (import.meta.env.VITE_ELEVENLABS_API_KEY || "").trim();

            console.log("🔑 API Key:", API_KEY ? `${API_KEY.substring(0, 6)}...` : "❌ MISSING");
            console.log(`🎤 Voice: ${voiceName} (${voiceId})`);

            if (!API_KEY) {
                throw new Error("VITE_ELEVENLABS_API_KEY is not set in .env.");
            }

            console.log("📡 Requesting ElevenLabs TTS...");
            const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'xi-api-key': API_KEY,
                    'Accept': 'audio/mpeg'
                },
                body: JSON.stringify({
                    text: text,
                    model_id: "eleven_multilingual_v2",
                    voice_settings: {
                        stability: 0.6,
                        similarity_boost: 0.8,
                        style: 0.4,
                        use_speaker_boost: true
                    }
                })
            });

            console.log("📥 ElevenLabs Status:", response.status);

            if (!response.ok) {
                const errorBody = await response.text();
                let detail = "";
                try { detail = JSON.parse(errorBody)?.detail?.message || errorBody; } catch { detail = errorBody; }
                throw new Error(`ElevenLabs ${response.status}: ${detail}`);
            }

            const blob = await response.blob();
            console.log("📎 Audio blob size:", blob.size, "bytes");

            // Clean up old blob URL
            if (audioBlobUrl) URL.revokeObjectURL(audioBlobUrl);
            
            const url = URL.createObjectURL(blob);
            setAudioBlobUrl(url);

            // Use the always-mounted <audio> element via ref
            const audio = audioRef.current!;
            audio.src = url;
            audio.volume = 1.0;

            // Play it
            try {
                await audio.play();
                console.log("✅ audio.play() succeeded!");
                setAutoplayBlocked(false);
            } catch (playErr) {
                console.warn("⚠️ Autoplay blocked by browser. Showing manual play button.", playErr);
                setAutoplayBlocked(true);
                setIsSpeaking(false);
            }

        } catch (err: any) {
            console.error("🚨 TTS Error:", err);
            alert(`ElevenLabs failed: ${err.message || err}\n\nFalling back to browser speech.`);
            setIsSpeaking(false);

            const speech = new SpeechSynthesisUtterance(text);
            speech.onend = () => setIsSpeaking(false);
            speech.onerror = () => setIsSpeaking(false);
            window.speechSynthesis.speak(speech);
        }
    };

    const handleTranslateAndSpeak = async (lang: string) => {
        console.log(`🌐 handleTranslateAndSpeak triggered for language: ${lang}`);
        setIsTranslating(true);
        setShowLangMenu(false);
        try {
            console.log("🤖 Translation via Gemini started...");
            const translationKey = import.meta.env.VITE_TRANSLATION_API_KEY;
            const genAI = new GoogleGenerativeAI(translationKey);
            const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
            const prompt = `Translate the following lease expert review bullet points into ${lang}. Keep the same list format. Return ONLY the translated text: ${analysis.overview_text}`;

            const result = await model.generateContent(prompt);
            const response = await result.response;
            const text = response.text();

            console.log("✅ Translation received:", text.substring(0, 50) + "...");
            setTranslatedText(text);
            setCurrentLanguage(lang);
            setIsTranslating(false);

            console.log("🎙️ Moving to Speech Flow...");
            await handleSpeak(text, lang);
        } catch (err) {
            console.error("🚨 Translation/Speech Flow failure:", err);
            setIsTranslating(false);
            setIsSpeaking(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-[#FDF8F5] border-[3px] border-[#5A4231] rounded-[2rem] shadow-[8px_8px_0_0_#5A4231] overflow-hidden">
            <div className="flex border-b-[3px] border-[#5A4231] bg-[#F2E3D5] p-1.5 gap-1.5">
                <button
                    onClick={() => onSelectTab('overview')}
                    className={`flex-1 flex items-center justify-center py-3 rounded-2xl font-black text-xs uppercase tracking-wider transition-all ${activeTab === 'overview' ? 'bg-[#D9734E] text-white shadow-[2px_2px_0_0_#5A4231]' : 'bg-white/50 text-[#8A6B53] hover:bg-white hover:text-[#D9734E]'}`}
                >
                    Overview
                </button>
                <button
                    onClick={() => onSelectTab('details')}
                    className={`flex-1 flex items-center justify-center py-3 rounded-2xl font-black text-xs uppercase tracking-wider transition-all ${activeTab === 'details' ? 'bg-[#D9734E] text-white shadow-[2px_2px_0_0_#5A4231]' : 'bg-white/50 text-[#8A6B53] hover:bg-white hover:text-[#D9734E]'}`}
                >
                    Analysis
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 md:p-8 custom-scrollbar">
                {activeTab === 'overview' ? (
                    <div className="space-y-8 animate-in fade-in duration-500">
                        {/* Financials & Basic Info */}
                        <div className="space-y-2">
                            <DataRow label="Property Address" field={analysis.address} />
                            <DataRow label="Monthly Rent" field={analysis.rent_monthly} />
                            <DataRow label="Security Deposit" field={analysis.security_deposit} />
                            <DataRow label="Late Fees" field={analysis.late_fees} />
                            <DataRow label="Break Clause" field={analysis.early_termination} />
                            <DataRow label="Utilities/Keys" field={analysis.utilities} />
                            <DataRow label="Lease Duration" field={analysis.lease_term_days} suffix=" Days" />
                            <DataRow label="Notice Period" field={analysis.notice_period} />
                        </div>

                        {/* Summary Section */}
                        <div className="pt-6">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-xs font-black uppercase tracking-widest text-[#4A3424]">Expert Review</h3>
                                <div className="flex items-center gap-3">
                                    <button
                                        onClick={handleTestAudio}
                                        className="text-[9px] font-black uppercase tracking-tighter text-[#8A6B53] hover:text-[#D9734E] flex items-center gap-1 opacity-50 hover:opacity-100 transition-all font-mono"
                                        title="Click if you can't hear anything"
                                    >
                                        <AlertCircle size={10} /> Test Sound
                                    </button>
                                    <div className="relative">
                                        <button
                                            onClick={() => setShowLangMenu(!showLangMenu)}
                                            className="text-[9px] font-black uppercase tracking-tighter text-[#8A6B53] hover:text-[#D9734E] transition-all"
                                        >
                                            Translate • {currentLanguage}
                                        </button>
                                        {showLangMenu && (
                                            <div className="absolute top-full right-0 mt-2 w-40 bg-white border-[3px] border-[#5A4231] rounded-2xl shadow-[4px_4px_0_0_#5A4231] z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                                                {currentLanguage !== 'English' && (
                                                    <button onClick={() => { setTranslatedText(null); setCurrentLanguage('English'); setShowLangMenu(false); }} className="w-full text-left px-4 py-2 text-[10px] font-black uppercase hover:bg-[#F2E3D5] transition-all border-b border-[#5A4231]/10">English (Reset)</button>
                                                )}
                                                {languages.map(l => (
                                                    <button key={l.code} onClick={() => handleTranslateAndSpeak(l.name)} className="w-full text-left px-4 py-2 text-[10px] font-black uppercase hover:bg-[#F2E3D5] transition-all border-b border-[#5A4231]/10 last:border-0">{l.name}</button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                    <button
                                        onClick={() => handleSpeak(translatedText || analysis.overview_text, currentLanguage)}
                                        disabled={isSpeaking}
                                        className={`text-[9px] font-black uppercase tracking-tighter transition-all ${isSpeaking ? 'text-[#D9734E] animate-pulse' : 'text-[#8A6B53] hover:text-[#D9734E]'}`}
                                    >
                                        {isSpeaking ? 'Speaking...' : 'Listen'}
                                    </button>
                                </div>
                            </div>

                            {/* Audio player - ALWAYS in DOM so Chrome allows playback */}
                            <div className={`mb-4 ${showAudioPlayer ? '' : 'hidden'}`}>
                                {autoplayBlocked && (
                                    <button
                                        onClick={() => {
                                            if (audioRef.current) {
                                                audioRef.current.play().then(() => {
                                                    setAutoplayBlocked(false);
                                                    setIsSpeaking(true);
                                                }).catch(e => console.error('Still blocked:', e));
                                            }
                                        }}
                                        className="w-full mb-2 py-4 bg-[#D9734E] text-white font-black text-sm uppercase tracking-wider rounded-2xl border-[3px] border-[#5A4231] shadow-[4px_4px_0_0_#5A4231] hover:shadow-[2px_2px_0_0_#5A4231] hover:translate-x-[2px] hover:translate-y-[2px] transition-all active:shadow-none active:translate-x-1 active:translate-y-1 animate-pulse"
                                    >
                                        🔊 Click Here to Play Audio ({speakingLanguage})
                                    </button>
                                )}
                                <div className="p-3 bg-white/80 rounded-2xl border border-[#5A4231]/10">
                                    <div className="flex items-center justify-between mb-2">
                                        <p className="text-[9px] font-black uppercase tracking-widest text-[#8A6B53]">Audio Player ({speakingLanguage}):</p>
                                        {audioBlobUrl && (
                                            <a
                                                href={audioBlobUrl}
                                                download={`lease-review-${speakingLanguage.toLowerCase()}.mp3`}
                                                className="text-[9px] font-black uppercase tracking-tighter text-[#D9734E] hover:underline"
                                            >
                                                ⬇ Download MP3
                                            </a>
                                        )}
                                    </div>
                                    <audio
                                        ref={audioRef}
                                        controls
                                        onPlay={() => { setIsSpeaking(true); setAutoplayBlocked(false); }}
                                        onEnded={() => { setIsSpeaking(false); }}
                                        onError={(e) => console.error("❌ Audio error:", e)}
                                        style={{ width: '100%', height: '40px' }}
                                    />
                                </div>
                            </div>

                            {isTranslating ? (
                                <div className="py-8 text-center bg-[#F2E3D5]/20 rounded-3xl animate-pulse">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-[#8A6B53]">Translating analysis...</p>
                                </div>
                            ) : (
                                <div className="bg-[#F2E3D5]/30 p-6 rounded-[2rem] border-[2px] border-[#5A4231]/5 group hover:border-[#D9734E]/10 transition-all relative">
                                    <div className="space-y-3">
                                        {(translatedText || analysis.overview_text).split(/\n|•|- /).filter(line => line.trim().length > 3).map((line, idx) => (
                                            <div key={idx} className="flex gap-3 items-start">
                                                <div className="w-1.5 h-1.5 rounded-full bg-[#D9734E] shrink-0 mt-1.5" />
                                                <p className="font-bold text-[#5A4231] text-[14px] leading-relaxed">
                                                    {line.trim().replace(/^[-•]\s*/, '')}
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="animate-in fade-in slide-in-from-right-4 duration-500 h-full">
                        {selectedHighlight ? (
                            <div className="space-y-8">
                                <div className="flex flex-col gap-4">
                                    <div className="flex items-center justify-between">
                                        <span className="text-[9px] font-black uppercase tracking-[0.2em] text-[#8A6B53]">{selectedHighlight.category}</span>
                                        <div className="flex gap-2">
                                            {selectedHighlight.severity && (
                                                <span className={`text-[8px] font-black uppercase px-2 py-1 rounded-full border-[1.5px] ${selectedHighlight.severity === 'HIGH' ? 'bg-rose-50 border-rose-500 text-rose-600' :
                                                    selectedHighlight.severity === 'MEDIUM' ? 'bg-amber-50 border-amber-500 text-amber-600' :
                                                        'bg-blue-50 border-blue-500 text-blue-600'
                                                    }`}>
                                                    {selectedHighlight.severity} RISK
                                                </span>
                                            )}
                                            <RiskBadge level={selectedHighlight.level} />
                                        </div>
                                    </div>
                                    <h3 className="text-2xl font-black text-[#4A3424] leading-tight">
                                        {selectedHighlight.title}
                                    </h3>
                                </div>

                                <div className="bg-[#5A4231] text-[#FDF8F5] rounded-[1.5rem] p-6 shadow-[5px_5px_0_0_#D9734E]">
                                    <h4 className="font-black text-[10px] uppercase tracking-widest mb-3 opacity-60">Impact Analysis</h4>
                                    <p className="font-bold leading-relaxed text-[15px]">
                                        {selectedHighlight.explanation}
                                    </p>
                                </div>

                                <div className="bg-white p-5 rounded-3xl border border-[#5A4231]/10 shadow-sm">
                                    <div className="font-black text-[9px] uppercase tracking-widest text-[#8A6B53] mb-3">Evidence Quote</div>
                                    <p className="italic font-medium text-[#5A4231] text-[14px] leading-relaxed">
                                        "{selectedHighlight.quote}"
                                    </p>
                                    {selectedHighlight.evidence_location_hint && (
                                        <div className="mt-3 text-[9px] font-black uppercase tracking-tighter text-[#8A6B53]/60">
                                            Found near: {selectedHighlight.evidence_location_hint}
                                        </div>
                                    )}
                                </div>

                                <div className="space-y-4 pt-4 border-t border-[#5A4231]/10">
                                    <h4 className="font-black text-[#4A3424] text-[10px] uppercase tracking-widest">Recommended Questions</h4>
                                    <div className="space-y-2">
                                        {selectedHighlight.suggestedQuestions.map((q, i) => (
                                            <div key={i} className="bg-[#F2E3D5]/20 p-4 rounded-2xl font-bold text-[13px] text-[#5A4231] flex items-center gap-3 border border-transparent hover:border-[#D9734E]/20 transition-all cursor-default">
                                                <span className="w-1.5 h-1.5 rounded-full bg-[#D9734E] shrink-0" />
                                                {q}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-center p-8 py-20">
                                <h3 className="text-lg font-black text-[#4A3424] mb-2 uppercase tracking-tight opacity-20">Select a Clause</h3>
                                <p className="font-bold text-[#8A6B53] text-[13px] opacity-40 leading-relaxed max-w-[200px]">Click any highlighted section in the document to see our legal breakdown.</p>
                            </div>
                        )}
                    </div>
                )}
            </div>

            <div className="p-4 bg-[#F2E3D5] border-t-[3px] border-[#5A4231] text-center">
                <p className="text-[9px] font-black uppercase tracking-widest text-[#8A6B53]/70">
                    Proprietary Lens Analysis • Not Legal Counsel
                </p>
            </div>

            <style>{`
                .custom-scrollbar::-webkit-scrollbar { width: 6px; }
                .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
                .custom-scrollbar::-webkit-scrollbar-thumb { background: #5A423115; border-radius: 20px; }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #5A423130; }
            `}</style>
        </div>
    );
}
