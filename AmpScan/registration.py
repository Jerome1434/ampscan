# -*- coding: utf-8 -*-
"""
Created on Wed Sep 13 16:07:10 2017

@author: js22g12
"""
import numpy as np
import copy
from scipy import spatial
from .core import AmpObject

class registration(object):
    """
    Class for registration of two AmpObjects
    
    Parameters
    ----------
    baseline: AmpObject
    	The baseline AmpObject, the vertices from this will be morphed onto the target
    target: AmpObject
    	The target AmpObject, the shape that the baseline attempts to morph onto
    method: str
    	A string of the method used for registration
    *args:
    	The arguments used for the registration methods
    **kwargs:
    	The keyword arguments used for the registration methods
    """ 
    def __init__(self, baseline, target, method='point2plane', *args, **kwargs):
        self.b = baseline
        self.t = target
        if method is not None:
            getattr(self, method)(*args, **kwargs)
        
        
    def point2plane(self, steps = 1, subset = None, neigh = 10, inside = True, smooth=1, fixBrim=False):
        """
        Function to register the regObject to the baseline mesh
        
        Need to add test to ensure inside triangle, currently not performing
        that so ending up in weird places on plane 
        
        Parameters
        ----------
        Steps: int, default 1
            Number of iterations
        """
        if fixBrim is True:
            eidx = (self.b.faceEdges == -99999).sum(axis=1).astype(bool)
            vBrim = np.unique(self.b.edges[eidx, :])
        # Calc FaceCentroids
        fC = self.t.vert[self.t.faces].mean(axis=1)
        # Construct knn tree
        tTree = spatial.cKDTree(fC)
        bData = dict(zip(['vert', 'faces', 'values'], 
                         [self.b.vert, self.b.faces, self.b.values]))
        regData = copy.deepcopy(bData)
        self.reg = AmpObject(regData, stype='reg')
        normals = np.cross(self.t.vert[self.t.faces[:,1]] -
                         self.t.vert[self.t.faces[:,0]],
                         self.t.vert[self.t.faces[:,2]] -
                         self.t.vert[self.t.faces[:,0]])
        mag = (normals**2).sum(axis=1)
        if subset is None:
            rVert = self.reg.vert
        else:
            rVert = self.reg.vert[subset]
        for step in np.arange(steps, 0, -1, dtype=float):
            # Index of 10 centroids nearest to each baseline vertex
            ind = tTree.query(rVert, neigh)[1]
#            D = np.zeros(self.reg.vert.shape)
            # Define normals for faces of nearest faces
            norms = normals[ind]
            # Get a point on each face
            fPoints = self.t.vert[self.t.faces[ind, 0]]
            # Calculate dot product between point on face and normals
            d = np.einsum('ijk, ijk->ij', norms, fPoints)
            t = (d - np.einsum('ijk, ik->ij', norms, rVert))/mag[ind]
            # Calculate the vector from old point to new point
            G = rVert[:, None, :] + np.einsum('ijk, ij->ijk', norms, t)
            # Ensure new points lie inside points otherwise set to 99999
            # Find smallest distance from old to new point 
            if inside is False:
                G = G - rVert[:, None, :]
                GMag = np.sqrt(np.einsum('ijk, ijk->ij', G, G))
                GInd = GMag.argmin(axis=1)
            else:
                G, GInd = self.calcBarycentric(rVert, G, ind)
            # Define vector from baseline point to intersect point
            D = G[np.arange(len(G)), GInd, :]
            rVert += D/step
            if smooth > 0 and step > 1:
                if fixBrim is True:
                    bPoints = rVert[vBrim, :].copy()
#                v = self.reg.vert[~subset]
                    self.reg.lp_smooth(smooth)
                    self.reg.vert[vBrim, :] = bPoints
#                self.reg.vert[~subset] = v
                else:
                    self.reg.lp_smooth(smooth)
            else:
                self.reg.calcNorm()
        
        self.reg.calcStruct()
#        self.reg.values[:] = self.calcError(False)
        self.reg.values[:] = self.calcError(False)
        
    def calcError(self, direct):
        """
        A function within a function will not be documented

        """
        if direct is True:
            self.b.calcVNorm()
            values = np.linalg.norm(self.reg.vert - self.b.vert, axis=1)
            # Calculate the unit vector normal between corresponding vertices
            # baseline and target
            vector = (self.reg.vert - self.b.vert)/values[:, None]
            # Calculate angle between the two unit vectors using normal of cross
            # product between vNorm and vector and dot
            normcrossP = np.linalg.norm(np.cross(vector, self.b.vNorm), axis=1)
            dotP = np.einsum('ij,ij->i', vector, self.b.vNorm)
            angle = np.arctan2(normcrossP, dotP)
            polarity = np.ones(angle.shape)
            polarity[angle < np.pi/2] =-1.0
            values = values * polarity
            return values
        else:
            values = np.linalg.norm(self.reg.vert - self.b.vert, axis=1)
            return values
        
    def calcBarycentric(self, vert, G, ind):
        P0 = self.t.vert[self.t.faces[ind, 0]]
        P1 = self.t.vert[self.t.faces[ind, 1]]
        P2 = self.t.vert[self.t.faces[ind, 2]]
        
        v0 = P2 - P0
        v1 = P1 - P0
        v2 = G - P0
        
        d00 = np.einsum('ijk, ijk->ij', v0, v0)
        d01 = np.einsum('ijk, ijk->ij', v0, v1)
        d02 = np.einsum('ijk, ijk->ij', v0, v2)
        d11 = np.einsum('ijk, ijk->ij', v1, v1)
        d12 = np.einsum('ijk, ijk->ij', v1, v2)
        
        denom = d00*d11 - d01*d01
        u = (d11 * d02 - d01 * d12)/denom
        v = (d00 * d12 - d01 * d02)/denom
        # Test if inside 
        logic = (u >= 0) * (v >= 0) * (u + v < 1)
        
        P = np.stack([P0, P1, P2], axis=3)
        pg = G[:, :, :, None] - P
        pd =  np.linalg.norm(pg, axis=2)
        pdx = pd.argmin(axis=2)
        i, j = np.meshgrid(np.arange(P.shape[0]), np.arange(P.shape[1]))
        nearP = P[i.T, j.T, :, pdx]
        G[~logic, :] = nearP[~logic, :]
        G = G - vert[:, None, :]
        GMag = np.sqrt(np.einsum('ijk, ijk->ij', G, G))
        GInd = GMag.argmin(axis=1)
        return G, GInd
