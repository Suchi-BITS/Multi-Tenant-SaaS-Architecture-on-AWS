/**
 * Dashboard Component
 * 
 * Main dashboard showing tenant statistics and overview
 * Demonstrates tenant-aware data visualization
 */

import React, { useState, useEffect } from 'react';
import ApiService from '../services/apiService';
import './Dashboard.css';

function Dashboard({ user }) {
  const [stats, setStats] = useState({
    totalProducts: 0,
    totalOrders: 0,
    pendingOrders: 0,
    revenue: 0
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      const dashboardStats = await ApiService.getDashboardStats();
      setStats(dashboardStats);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(amount);
  };

  if (loading) {
    return (
      <div className="dashboard-container">
        <div className="loading">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h1>Dashboard</h1>
        <div className="tenant-info">
          <span className="tenant-badge">{user.tenant_tier.toUpperCase()}</span>
          <span className="tenant-id">Tenant: {user.tenant_id.substring(0, 8)}...</span>
        </div>
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon products-icon">📦</div>
          <div className="stat-content">
            <h3>Total Products</h3>
            <p className="stat-number">{stats.totalProducts}</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon orders-icon">📋</div>
          <div className="stat-content">
            <h3>Total Orders</h3>
            <p className="stat-number">{stats.totalOrders}</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon pending-icon">⏳</div>
          <div className="stat-content">
            <h3>Pending Orders</h3>
            <p className="stat-number">{stats.pendingOrders}</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon revenue-icon">💰</div>
          <div className="stat-content">
            <h3>Total Revenue</h3>
            <p className="stat-number">{formatCurrency(stats.revenue)}</p>
          </div>
        </div>
      </div>

      <div className="dashboard-content">
        <div className="info-section">
          <h2>Welcome to Your Multi-Tenant SaaS Dashboard</h2>
          <p>
            This dashboard demonstrates key concepts of a serverless multi-tenant SaaS application:
          </p>

          <div className="feature-list">
            <div className="feature-item">
              <h3>Tenant Isolation</h3>
              <p>
                All data is automatically isolated by tenant. Your products and orders
                are completely separate from other tenants.
              </p>
            </div>

            <div className="feature-item">
              <h3>Tier-Based Access</h3>
              <p>
                Your current tier is <strong>{user.tenant_tier}</strong>. 
                Different tiers have different limits and features.
              </p>
            </div>

            <div className="feature-item">
              <h3>Serverless Architecture</h3>
              <p>
                Built with AWS Lambda, API Gateway, DynamoDB, and Cognito for
                scalability and cost-efficiency.
              </p>
            </div>

            <div className="feature-item">
              <h3>Real-Time Monitoring</h3>
              <p>
                CloudWatch metrics track API calls, errors, and performance
                per tenant for observability.
              </p>
            </div>
          </div>
        </div>

        <div className="quick-actions">
          <h2>Quick Actions</h2>
          <div className="action-buttons">
            <a href="/products" className="action-btn">
              <span>📦</span>
              Manage Products
            </a>
            <a href="/orders" className="action-btn">
              <span>📋</span>
              View Orders
            </a>
            <a href="/settings" className="action-btn">
              <span>⚙️</span>
              Tenant Settings
            </a>
          </div>
        </div>

        <div className="architecture-info">
          <h2>Architecture Highlights</h2>
          <div className="architecture-grid">
            <div className="arch-item">
              <h4>API Gateway</h4>
              <p>RESTful API with Cognito authorization</p>
            </div>
            <div className="arch-item">
              <h4>Lambda Functions</h4>
              <p>Separate functions for each operation</p>
            </div>
            <div className="arch-item">
              <h4>DynamoDB</h4>
              <p>NoSQL database with tenant partitioning</p>
            </div>
            <div className="arch-item">
              <h4>Cognito</h4>
              <p>User authentication and management</p>
            </div>
            <div className="arch-item">
              <h4>CloudWatch</h4>
              <p>Logging and monitoring per tenant</p>
            </div>
            <div className="arch-item">
              <h4>IAM</h4>
              <p>Fine-grained access control</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
