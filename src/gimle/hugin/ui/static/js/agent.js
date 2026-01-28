/* Agent Page - Standalone View JavaScript */

// Artifact data from Python (injected as {{ARTIFACTS_JSON}})
// const artifactsData = {};

// Store currently selected interaction
let currentSelectedBox = null;

// Panel size state: 'normal' -> 'wide' -> 'fullscreen' -> 'normal'
let currentPanelSize = 'normal';

function showArtifacts(boxElement) {
    // Get interaction ID from the parent flowchart-item
    const flowchartItem = boxElement.closest('.flowchart-item');
    const interactionId = flowchartItem.getAttribute('data-interaction-id');

    // Check if this interaction has artifacts
    if (!artifactsData[interactionId] || artifactsData[interactionId].length === 0) {
        return;
    }

    // Remove previous selection
    if (currentSelectedBox) {
        currentSelectedBox.classList.remove('flowchart-box-selected');
    }

    // Mark this box as selected
    boxElement.classList.add('flowchart-box-selected');
    currentSelectedBox = boxElement;

    // Get artifacts for this interaction
    const artifacts = artifactsData[interactionId];

    // Build artifact HTML
    let artifactHTML = '';
    artifacts.forEach((artifact, index) => {
        artifactHTML += `
            <div class="artifact-panel-item">
                <div class="artifact-panel-item-header">
                    <h4>Artifact ${index + 1}: ${artifact.type}</h4>
                    <span class="artifact-panel-item-id">ID: ${artifact.id}</span>
                </div>
                <div class="artifact-panel-item-content">
                    ${artifact.html}
                </div>
            </div>
        `;
    });

    // Update panel content
    document.getElementById('artifact-panel-content').innerHTML = artifactHTML;

    // Show the panel
    const panel = document.getElementById('artifact-panel');
    const wrapper = document.querySelector('.main-content-wrapper');
    panel.classList.add('artifact-panel-open');
    wrapper.classList.add('artifact-panel-open');
}

function closeArtifactPanel() {
    const panel = document.getElementById('artifact-panel');
    const wrapper = document.querySelector('.main-content-wrapper');
    panel.classList.remove('artifact-panel-open');
    panel.classList.remove('artifact-panel-wide');
    panel.classList.remove('artifact-panel-fullscreen');
    wrapper.classList.remove('artifact-panel-open');
    wrapper.classList.remove('artifact-panel-wide');
    wrapper.classList.remove('artifact-panel-fullscreen');
    currentPanelSize = 'normal';
    updateExpandButton();
    if (currentSelectedBox) {
        currentSelectedBox.classList.remove('flowchart-box-selected');
        currentSelectedBox = null;
    }
}

function togglePanelSize() {
    const panel = document.getElementById('artifact-panel');
    const wrapper = document.querySelector('.main-content-wrapper');

    // Remove all size classes first
    panel.classList.remove('artifact-panel-wide');
    panel.classList.remove('artifact-panel-fullscreen');
    wrapper.classList.remove('artifact-panel-wide');
    wrapper.classList.remove('artifact-panel-fullscreen');

    // Cycle through sizes
    if (currentPanelSize === 'normal') {
        currentPanelSize = 'wide';
        panel.classList.add('artifact-panel-wide');
        wrapper.classList.add('artifact-panel-wide');
    } else if (currentPanelSize === 'wide') {
        currentPanelSize = 'fullscreen';
        panel.classList.add('artifact-panel-fullscreen');
        wrapper.classList.add('artifact-panel-fullscreen');
    } else {
        currentPanelSize = 'normal';
    }
    updateExpandButton();
}

function updateExpandButton() {
    const btn = document.querySelector('.artifact-panel-expand');
    if (!btn) return;
    if (currentPanelSize === 'normal') {
        btn.textContent = 'Expand';
    } else if (currentPanelSize === 'wide') {
        btn.textContent = 'Fullscreen';
    } else {
        btn.textContent = 'Collapse';
    }
}

function showInteractionDetails(interactionId, scrollToArtifacts) {
    // For standalone agent page, just show artifacts
    const flowchartItem = document.querySelector(`[data-interaction-id="${interactionId}"]`);
    if (flowchartItem) {
        const box = flowchartItem.querySelector('.flowchart-box');
        if (box) {
            showArtifacts(box);
        }
    }
}

// Close panel when clicking outside
document.addEventListener('click', function(event) {
    const panel = document.getElementById('artifact-panel');
    if (!panel) return;

    const wrapper = document.querySelector('.main-content-wrapper');
    const isClickInsidePanel = panel.contains(event.target);
    const isClickOnFlowchartBox = event.target.closest('.flowchart-box-clickable');

    if (!isClickInsidePanel && !isClickOnFlowchartBox && panel.classList.contains('artifact-panel-open')) {
        closeArtifactPanel();
    }
});

// Initialize collapsible sections on page load
document.addEventListener('DOMContentLoaded', function() {
    // Make Artifacts List section collapsible
    const artifactsSection = document.querySelector('.artifacts-list-section');
    if (artifactsSection) {
        const header = artifactsSection.querySelector('h2');
        const content = artifactsSection.querySelector('.artifacts-list-content');
        if (header && content) {
            header.onclick = function(e) {
                e.stopPropagation();
                header.classList.toggle('expanded');
                content.classList.toggle('expanded');
            };
        }

        // Add click handlers to artifact items
        document.querySelectorAll('.artifacts-list-item').forEach(item => {
            item.onclick = function(e) {
                if (e.target.closest('.artifacts-list-item-interaction')) {
                    return;
                }
                const interactionId = item.getAttribute('data-interaction-id');
                if (interactionId) {
                    showInteractionDetails(interactionId, true);
                }
            };
        });
    }
});
