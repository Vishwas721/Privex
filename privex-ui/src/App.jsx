import React from 'react';

function App() {
  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-4xl mx-auto">
        
        {/* Header */}
        <header className="mb-10 border-b border-gray-700 pb-4">
          <h1 className="text-3xl font-bold text-blue-400">Privex</h1>
          <p className="text-gray-400 mt-2">Privacy-First Personal AI Guardian</p>
        </header>

        {/* Approval Queue Section */}
        <section>
          <h2 className="text-xl font-semibold mb-4 text-gray-200">Action Approval Queue</h2>
          
          {/* Mock Alert Card */}
          <div className="bg-gray-800 border border-red-500 rounded-lg p-6 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <span className="bg-red-500/20 text-red-400 px-3 py-1 rounded-full text-sm font-medium tracking-wide border border-red-500/50">
                CRITICAL RISK
              </span>
              <span className="text-gray-400 text-sm">Just now</span>
            </div>
            
            <p className="text-lg mb-6">
              <strong>Phishing Agent</strong> detected a malicious URL in an open email. 
              The AI proposes closing the tab and deleting the email.
            </p>
            
            <div className="flex space-x-4">
              <button className="bg-red-600 hover:bg-red-700 text-white px-6 py-2 rounded font-medium transition-colors">
                Block Action
              </button>
              <button className="bg-green-600 hover:bg-green-700 text-white px-6 py-2 rounded font-medium transition-colors">
                Approve Action
              </button>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}

export default App;