/**
 * API Service
 * 
 * Handles all API calls to the backend services:
 * - Product management
 * - Order management
 * - Tenant operations
 * 
 * Includes automatic token refresh and tenant isolation
 */

import axios from 'axios';
import AuthService from './authService';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.example.com';

// Create axios instance with default config
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// Request interceptor to add auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = AuthService.getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If error is 401 and we haven't retried yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Try to refresh token
        await AuthService.refreshToken();
        
        // Retry original request with new token
        const token = AuthService.getAccessToken();
        originalRequest.headers.Authorization = `Bearer ${token}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed, logout user
        AuthService.logout();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

class ApiService {
  // ===== Product Operations =====

  /**
   * Lists all products for the current tenant
   */
  async getProducts(params = {}) {
    try {
      const response = await apiClient.get('/products', { params });
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to fetch products');
    }
  }

  /**
   * Gets a specific product by ID
   */
  async getProduct(productId) {
    try {
      const response = await apiClient.get(`/products/${productId}`);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to fetch product');
    }
  }

  /**
   * Creates a new product
   */
  async createProduct(productData) {
    try {
      const response = await apiClient.post('/products', productData);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to create product');
    }
  }

  /**
   * Updates an existing product
   */
  async updateProduct(productId, productData) {
    try {
      const response = await apiClient.put(`/products/${productId}`, productData);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to update product');
    }
  }

  /**
   * Deletes a product
   */
  async deleteProduct(productId) {
    try {
      const response = await apiClient.delete(`/products/${productId}`);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to delete product');
    }
  }

  // ===== Order Operations =====

  /**
   * Lists all orders for the current tenant
   */
  async getOrders(params = {}) {
    try {
      const response = await apiClient.get('/orders', { params });
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to fetch orders');
    }
  }

  /**
   * Gets a specific order by ID
   */
  async getOrder(orderId) {
    try {
      const response = await apiClient.get(`/orders/${orderId}`);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to fetch order');
    }
  }

  /**
   * Creates a new order
   */
  async createOrder(orderData) {
    try {
      const response = await apiClient.post('/orders', orderData);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to create order');
    }
  }

  /**
   * Updates order status
   */
  async updateOrderStatus(orderId, status) {
    try {
      const response = await apiClient.put(`/orders/${orderId}`, { status });
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to update order');
    }
  }

  // ===== Tenant Operations =====

  /**
   * Gets current tenant information
   */
  async getTenant() {
    try {
      const tenantId = AuthService.getTenantId();
      const response = await apiClient.get(`/tenants/${tenantId}`);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to fetch tenant information');
    }
  }

  /**
   * Updates tenant settings
   */
  async updateTenant(tenantData) {
    try {
      const tenantId = AuthService.getTenantId();
      const response = await apiClient.put(`/tenants/${tenantId}`, tenantData);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'Failed to update tenant');
    }
  }

  // ===== Dashboard Statistics =====

  /**
   * Gets dashboard statistics
   */
  async getDashboardStats() {
    try {
      // In a real implementation, this would be a dedicated endpoint
      // For now, we'll aggregate data from products and orders
      const [productsResponse, ordersResponse] = await Promise.all([
        this.getProducts({ limit: 1 }),
        this.getOrders({ limit: 1 })
      ]);

      // Calculate statistics
      const stats = {
        totalProducts: productsResponse.count || 0,
        totalOrders: ordersResponse.count || 0,
        pendingOrders: 0,
        revenue: 0
      };

      // Get detailed orders for revenue calculation
      const detailedOrders = await this.getOrders({ limit: 100 });
      
      if (detailedOrders.orders) {
        stats.pendingOrders = detailedOrders.orders.filter(
          order => order.status === 'pending'
        ).length;

        stats.revenue = detailedOrders.orders.reduce((sum, order) => {
          return sum + (parseFloat(order.total_amount) || 0);
        }, 0);
      }

      return stats;
    } catch (error) {
      throw this.handleError(error, 'Failed to fetch dashboard statistics');
    }
  }

  // ===== Error Handling =====

  handleError(error, defaultMessage) {
    const message = error.response?.data?.error || defaultMessage;
    const details = error.response?.data?.details;
    
    console.error(`API Error: ${message}`, details || '');
    
    return new Error(message);
  }
}

export default new ApiService();
export { ApiService };
