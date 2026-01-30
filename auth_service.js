/**
 * Authentication Service
 * 
 * Handles all authentication operations with AWS Cognito:
 * - Login
 * - Registration
 * - Logout
 * - Token management
 * - Session persistence
 */

import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.example.com';

class AuthService {
  /**
   * Registers a new user
   */
  async register(email, password, companyName, tier = 'basic') {
    try {
      // First, register the tenant
      const tenantResponse = await axios.post(`${API_BASE_URL}/tenants`, {
        company_name: companyName,
        admin_email: email,
        tier: tier,
        isolation_model: 'pool'
      });

      const tenantId = tenantResponse.data.tenant_id;

      // Then register the user with the tenant
      const userResponse = await axios.post(`${API_BASE_URL}/auth/signup`, {
        email: email,
        password: password,
        tenant_id: tenantId,
        given_name: companyName.split(' ')[0],
        family_name: companyName.split(' ')[1] || ''
      });

      return {
        success: true,
        message: 'Registration successful. Please check your email for verification.',
        tenant_id: tenantId
      };
    } catch (error) {
      console.error('Registration error:', error);
      throw new Error(error.response?.data?.error || 'Registration failed');
    }
  }

  /**
   * Logs in a user
   */
  async login(email, password) {
    try {
      const response = await axios.post(`${API_BASE_URL}/auth/signin`, {
        email: email,
        password: password
      });

      const authData = response.data;

      // Store auth data in localStorage
      localStorage.setItem('auth_data', JSON.stringify(authData));
      localStorage.setItem('access_token', authData.access_token);
      localStorage.setItem('id_token', authData.id_token);
      localStorage.setItem('refresh_token', authData.refresh_token);
      localStorage.setItem('tenant_id', authData.tenant_id);
      localStorage.setItem('tenant_tier', authData.tenant_tier);

      return authData;
    } catch (error) {
      console.error('Login error:', error);
      throw new Error(error.response?.data?.error || 'Login failed');
    }
  }

  /**
   * Logs out the current user
   */
  logout() {
    localStorage.removeItem('auth_data');
    localStorage.removeItem('access_token');
    localStorage.removeItem('id_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('tenant_id');
    localStorage.removeItem('tenant_tier');
  }

  /**
   * Gets the current user from localStorage
   */
  getCurrentUser() {
    const authData = localStorage.getItem('auth_data');
    return authData ? JSON.parse(authData) : null;
  }

  /**
   * Gets the access token
   */
  getAccessToken() {
    return localStorage.getItem('access_token');
  }

  /**
   * Gets the tenant ID
   */
  getTenantId() {
    return localStorage.getItem('tenant_id');
  }

  /**
   * Gets the tenant tier
   */
  getTenantTier() {
    return localStorage.getItem('tenant_tier');
  }

  /**
   * Checks if user is authenticated
   */
  isAuthenticated() {
    return !!this.getAccessToken();
  }

  /**
   * Refreshes the access token
   */
  async refreshToken() {
    try {
      const refreshToken = localStorage.getItem('refresh_token');
      
      if (!refreshToken) {
        throw new Error('No refresh token available');
      }

      const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
        refresh_token: refreshToken
      });

      const { access_token, id_token } = response.data;

      // Update tokens in localStorage
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('id_token', id_token);

      return access_token;
    } catch (error) {
      console.error('Token refresh error:', error);
      this.logout();
      throw error;
    }
  }

  /**
   * Initiates password reset
   */
  async forgotPassword(email) {
    try {
      await axios.post(`${API_BASE_URL}/auth/forgot-password`, {
        email: email
      });

      return {
        success: true,
        message: 'Password reset code sent to email'
      };
    } catch (error) {
      console.error('Forgot password error:', error);
      throw new Error(error.response?.data?.error || 'Password reset failed');
    }
  }

  /**
   * Confirms password reset with code
   */
  async resetPassword(email, code, newPassword) {
    try {
      await axios.post(`${API_BASE_URL}/auth/confirm-forgot-password`, {
        email: email,
        confirmation_code: code,
        new_password: newPassword
      });

      return {
        success: true,
        message: 'Password reset successful'
      };
    } catch (error) {
      console.error('Reset password error:', error);
      throw new Error(error.response?.data?.error || 'Password reset failed');
    }
  }
}

export default new AuthService();
export { AuthService };
